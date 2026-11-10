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


# ---------------------------------------------------------------- 역할 칸 행 묶음(② §12 — 「이름 (주관)」·「이름 (공동)」 칸)

def _role_groups(d, values):
    from app.division_profiles import _structure as structure
    blocks = d.blocks()
    idx = structure.index_blocks(blocks)
    return [(g, idx[g["table"]]) for g in rnd.find(blocks, rnd.levels_of(blocks), values) if g.get("roleRows")]


def _col(t, col, top=2):
    return [" ".join((c["text"] or "").split()) for c in sorted(t["cells"], key=lambda c: c["row"]) if c["col"] == col and c["row"] >= top]


def test_role_cell_rows_are_an_org_group():
    """7-1 (3) 「가. 참여연구자 현황」 — 「소속 기관 (역할)」 열의 「KEIT (주관)」·「KIAT (공동)」… 칸이 기관 행 묶음(2026-11-10 사용자 "이 테이블만 빠진듯").
    같은 이름 칸 둘(KETEP)은 한 기관 · 수가 같으면 이름만 · 늘리면 사본 + 번호 다시 · 줄이면 끝에서 지움 · 값에 없는 이름이 있으면 그대로."""
    from app import hwpx_doc
    V = lambda lead, joint: rnd.norm_values({"stages": [1], "orgs": {"lead": lead, "joint": joint}})  # noqa: E731
    d = hwpx_doc.HwpxDoc(FORM.read_bytes())
    v = V("가나", ["다라", "마바", "사아"])
    (g, t), = _role_groups(d, v)   # 빈 양식의 역할 칸 묶음은 이 표 하나(신규채용 표는 라벨 낱말 칸 — 칸 라벨 묶음 몫)
    assert (t["nRows"], t["nCols"]) == (9, 15) and g["dim"] == "org" and g["kind"] == "rows" and not g["irregular"]
    assert [it["value"] for it in g["items"]] == [("lead", 0), ("joint", 1), ("joint", 2), ("joint", 3)]
    assert [it["span"] for it in g["items"]] == [(2, 3), (4, 5), (6, 7), (8, 8)] and len(g["items"][2]["nameAts"]) == 2
    assert g["plan"]["copies"] == 0 and g["plan"]["drop"] == [] and not g["plan"]["done"]
    mg = next(x for x in rnd.members(d.blocks(), rnd.levels_of(d.blocks()), v)["groups"] if x["key"] == g["key"])   # 문서 표시에도 기관 자리로
    assert mg["dimName"] == "기관" and mg["kindName"] == "표 행" and [it["value"] for it in mg["items"]] == ["주관", "공동1", "공동2", "공동3"]
    assert all(it["paras"] for it in mg["items"])
    rep = rnd.apply(d, v, levels_of=rnd.levels_of, only=g["key"])
    assert not rep["errors"] and rep["added"] == rep["removed"] == 0
    assert sorted((c["old"], c["new"]) for c in rep["changes"]) == [("KEIT", "가나"), ("KETEP", "마바"), ("KETEP", "마바"), ("KIAT", "다라"), ("OO대학교", "사아")]
    (g, t), = _role_groups(d, v)
    assert g["plan"]["done"] and _col(t, 1) == ["가나 (주관)", "다라 (공동)", "마바 (공동)", "마바 (공동)", "사아 (공동)"]   # 역할 괄호는 그대로
    # 공동 5(마지막은 이름 없음) — 가장 큰 공동 항목 중 뒤(마바, 2행)를 둘 본뜨고 번호 열은 1부터 다시
    v = V("가나", ["다라", "마바", "사아", "자차", ""])
    (g, t), = _role_groups(d, v)
    rep = rnd.apply(d, v, levels_of=rnd.levels_of, only=g["key"])
    (g, t), = _role_groups(d, v)
    assert not rep["errors"] and rep["added"] == 2 and t["nRows"] == 13 and g["plan"]["done"]
    assert [" ".join(it["labelText"].split()) for it in g["items"]] == ["가나 (주관)", "다라 (공동)", "마바 (공동)", "사아 (공동)", "자차 (공동)", "참여기관5 (공동)"]
    assert _col(t, 0) == [str(k) for k in range(1, 11)]
    # 표에 구분 값에 없는 이름이 있으면(기관을 빼거나 이름을 바꾼 값) 작성한 표로 보고 그대로
    (g, t), = _role_groups(d, V("가나", ["다라"]))
    assert g["irregular"] and g["target"] is None and g["plan"] is None
    # 빈 양식에서 공동 1 — 남는 공동 항목은 끝에서부터 지움, 이름 없는 주관은 기본 이름
    d = hwpx_doc.HwpxDoc(FORM.read_bytes())
    v = V("", ["다라"])
    (g, t), = _role_groups(d, v)
    assert g["plan"]["drop"] == [2, 3]
    rep = rnd.apply(d, v, levels_of=rnd.levels_of, only=g["key"])
    (g, t), = _role_groups(d, v)
    assert not rep["errors"] and rep["removed"] == 2 and t["nRows"] == 6 and g["plan"]["done"]
    assert _col(t, 1) == ["주관기관(미입력) (주관)", "다라 (공동)"] and _col(t, 0) == ["1", "2", "3"]


def test_role_cell_tables_after_full_apply(flow):
    """전체 반영 뒤 같은 값 재계획(② §12): 참여연구자 현황 표와 이름이 들어간 신규채용 표(「인텍 (주관)」 — 라벨 낱말이 사라져 전에는 못 찾던 것)가
    둘 다 기관 자리로 다시 잡히고 이미 맞음."""
    cands = [c for c in flow["plan_same"]["candidates"] if c["dim"] == "org" and c["kind"] == "rows" and c["labels"][0] == "인텍 (주관)"]
    assert len(cands) == 2 and all(c["status"] == "already" and c["count"] == 3 for c in cands)
    assert all(c["labels"][1:] == ["참여기관1 (공동)", "한국선급 (공동)"] for c in cands)


# ---------------------------------------------------------------- 이름 든 기관 제목 줄 · 사업화 절 · 외 기관 절(② §15)

def test_named_org_labels_found_after_apply(flow):
    """전체 반영 뒤 같은 값 재계획: 이름이 들어간 기관 제목 줄(「[주관연구개발기관(인텍)]」·「[주관연구개발기관 : 인텍]」)이 다시 기관 문단 묶음으로 잡히고 이미 맞음 —
    전에는 이름 때문에 꼴이 갈려 사라졌다(2026-11-10 사용자 "판단되는 곳은 다 넣어줘"). 사업화 추진전략 「[… : 기업명1/2]」 도 자리표시가 달라도 한 묶음."""
    cands = [c for c in flow["plan_same"]["candidates"] if c["dim"] == "org" and c["kind"] == "paragraph"]
    paren = [c for c in cands if c["labels"][0] == "[주관연구개발기관(인텍)]"]
    colon = [c for c in cands if c["labels"][0].startswith("[주관연구개발기관 : 인텍]")]
    assert len(paren) >= 8 and len(colon) == 2 and all(c["status"] == "already" and c["count"] == 3 for c in paren + colon)
    assert all(c["labels"][1:] == ["[공동연구개발기관1(참여기관1)]", "[공동연구개발기관2(한국선급)]"] for c in paren)
    first = [c for c in flow["plan"]["candidates"] if c["labels"] and c["labels"][0].startswith("[주관연구개발기관 : 기업명1]")]   # 빈 양식의 첫 계획에서
    assert len(first) == 1 and first[0]["count"] == 2 and first[0]["target"] == 3 and first[0]["status"] == "applied"


def test_named_labels_follow_values_or_stay(flow):
    """반영본에서 값이 달라졌을 때(② §15): 기관을 더한 값이면 이름 든 기관 묶음이 그만큼 늘 목표를 갖고, 라벨에 **값에 없는 이름**이 남는 값(이름을 바꿈)이면
    작성한 문서로 보고 그대로(지원 안 됨)."""
    from app import hwpx_doc
    blocks = hwpx_doc.HwpxDoc(flow["after_bytes"]).blocks()
    lv = rnd.levels_of(blocks)
    named = lambda v: [g for g in rnd.find(blocks, lv, rnd.norm_values(v)) if g["dim"] == "org" and g["kind"] == "paragraph"  # noqa: E731
                       and "한국선급" in " ".join(it["labelText"] for it in g["items"])]
    more = named({"stages": [2, 3], "orgs": {"lead": "인텍", "joint": ["", "한국선급", "새기관"], "nonprofit": [False, False, True, False]}})
    assert len(more) >= 10 and all(not g["irregular"] and len(g["target"]) == 4 and g["plan"]["copies"] == 1 and not g["plan"]["drop"] for g in more)
    renamed = named({"stages": [2, 3], "orgs": {"lead": "인텍", "joint": ["", "선급"], "nonprofit": [False, False, True]}})
    assert len(renamed) == len(more) and all(g["irregular"] and g["target"] is None and g["plan"] is None for g in renamed)


def test_outside_org_sections_group():
    """7-1 라. 「연구개발기관 외 기관」 아래 「가. 기관명: (역할: )」·「나. 기관명: (역할: )」 제목 줄 + 표 한 벌 = 외 기관 묶음 — 3곳이면 하나 본뜨고 차례 글자·이름,
    0곳이면 다 지움(국외기관 묶음과 같게)."""
    from app import hwpx_doc
    d = hwpx_doc.HwpxDoc(FORM.read_bytes())
    V = lambda outside: rnd.norm_values({"stages": [1], "orgs": {"lead": "가나", "joint": ["다라"], "outside": outside}})  # noqa: E731

    def find(v):
        blocks = d.blocks()
        return next((g for g in rnd.find(blocks, rnd.levels_of(blocks), v) if g["dim"] == "org" and not g["table"] and g["items"][0]["value"][0] == "outside"), None)
    v = V(["한강청", "", "부산시"])
    g = find(v)
    assert [it["value"] for it in g["items"]] == [("outside", 1), ("outside", 2)] and [it["size"] for it in g["items"]] == [3, 3]   # 제목 줄 + 표 + 빈 줄
    assert g["target"] == [("outside", 1), ("outside", 2), ("outside", 3)] and g["plan"]["copies"] == 1 and not g["plan"]["drop"]
    rep = rnd.apply(d, v, levels_of=rnd.levels_of, only=g["key"])
    g = find(v)
    assert not rep["errors"] and rep["added"] == 1 and g["plan"]["done"] and [it["size"] for it in g["items"]] == [3, 3, 3]
    assert [" ".join(it["labelText"].split()) for it in g["items"]] == ["가. 기관명: 한강청 (역할: )", "나. 기관명: (역할: )", "다. 기관명: 부산시 (역할: )"]
    v = V([])
    g = find(v)
    assert g["target"] == [] and g["plan"]["drop"] == [0, 1, 2]
    rep = rnd.apply(d, v, levels_of=rnd.levels_of, only=g["key"])
    assert not rep["errors"] and rep["removed"] == 3 and find(v) is None


# ---------------------------------------------------------------- 빠진 자리 검토(② §13 — LLM 이 묶음 밖 표·문단을 본다)

MISSING_PARA = "(2) 주관/공동연구개발기관별"   # 빈 양식에서 아직 어느 묶음에도 안 든 문단(3-4 「(2) 주관/공동연구개발기관별 일자리 창출 계획」) — 가짜 응답이 가리킬 것

def test_llm_missing_review(monkeypatch):
    """묶음 밖 표·문단 요약을 보내고, 답은 보낸 id 만 받아 후보로 돌려준다(확신 순) — 판정만(rev·추가한 자리·계획 그대로), 기록·로그, 답이 없으면 502."""
    from app import division_llm, hwpx_doc
    from app.division_profiles.rnd import core
    server.DOCS.clear()
    c = TestClient(server.app)
    d = _open_form(c)
    seen = {}
    call = {"backend": "fake", "model": "m", "effort": "medium", "ms": 5, "costUsd": 0, "error": None}

    def fake(payload, *, call_=None, effort="medium", timeout=240.0):
        seen["payload"] = payload
        t = next(t for t in payload["tables"] if "소속 기관" in t["head"])   # 나. 연구지원인력 현황(역할 괄호 없는 사람 목록)
        p = next(p for p in payload["paragraphs"] if p["text"].startswith(MISSING_PARA))
        return {"data": {"missing": [
            {"id": p["id"], "dim": "org", "pattern": "절: 기관마다", "reason": "기관별 계획 제목", "confidence": "medium"},
            {"id": t["id"], "dim": "org", "pattern": "행: 소속 기관마다", "reason": "소속 기관 열", "confidence": "high"},
            {"id": t["id"], "dim": "org", "pattern": "x", "reason": "x", "confidence": "low"},
            {"id": "t-none", "dim": "org", "pattern": "x", "reason": "x", "confidence": "low"}], "summary": "두 곳"}, "prompt": "p", "call": call}
    monkeypatch.setattr(division_llm, "ask_missing", fake)
    before = c.get(f"/api/docs/{d}/divisions").json()
    r = c.post(f"/api/docs/{d}/divisions/llm_missing", json={})
    assert r.status_code == 200, r.text
    out, pl = r.json(), seen["payload"]
    assert out["sent"] == {"tables": len(pl["tables"]), "paragraphs": len(pl["paragraphs"])} and pl["tables"] and pl["paragraphs"] and pl["groups"]
    assert not any("KEIT (주관)" in t["marks"] for t in pl["tables"])   # 참여연구자 현황은 이제 묶음(② §12) — 묶음 안 표는 안 보낸다
    assert not any("작성요령" in t["head"][0].replace(" ", "")[:12] for t in pl["tables"] if t["head"])   # 작성요령 상자도
    assert not any(p["text"].startswith(("가. 기관명", "[주관연구개발기관 : 기업명1]")) for p in pl["paragraphs"])   # 외 기관 절·사업화 절도 이제 묶음(② §15)
    assert [x["kind"] for x in out["missing"]] == ["table", "paragraph"] and [x["confidence"] for x in out["missing"]] == ["high", "medium"]   # 확신 순
    assert out["missing"][0]["dimName"] == "기관" and out["missing"][0]["size"] and out["missing"][1]["text"].startswith(MISSING_PARA)
    assert [x["why"] for x in out["skipped"]] == ["같은 자리를 두 번", "보낸 자료에 없는 id"]
    assert out["summary"] == "두 곳" and out["call"]["backend"] == "fake" and out["detail"].startswith("divisions/missing_")
    after = c.get(f"/api/docs/{d}/divisions").json()
    assert after["rev"] == before["rev"] == out["rev"] and after["hints"] == [] and after["plan"] is None   # 세션 상태는 그대로
    monkeypatch.setattr(division_llm, "ask_missing", lambda payload, **k: {"data": None, "prompt": "p", "call": {**call, "error": "off"}})
    assert c.post(f"/api/docs/{d}/divisions/llm_missing", json={}).status_code == 502
    assert [x["kind"] for x in _log_events(c, d)].count("divisionMissing") == 2
    server.DOCS.clear()
    # 역할 칸 규칙이 없었다면(② §12 를 끈 채) 그 표가 자료에 실린다 — 사용자가 본 「KEIT (주관)」 칸이 표본에
    monkeypatch.setattr(core, "_role_rows", lambda t: [])
    blocks = hwpx_doc.HwpxDoc(FORM.read_bytes()).blocks()
    lv, v = rnd.levels_of(blocks), rnd.norm_values({"stages": [1], "orgs": {"lead": "", "joint": []}})
    pl2 = division_llm.missing_data(blocks, lv, v, rnd.find(blocks, lv, v), rnd.value_text)
    t = next(t for t in pl2["tables"] if "KEIT (주관)" in t["marks"])
    assert "소속 기관 (역할)" in t["head"] and t["title"].startswith("가. 참여연구자 현황")
