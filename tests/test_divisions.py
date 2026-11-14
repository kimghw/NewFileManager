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
    # 손상 파일 — 조회는 빈 목록 + broken, 고치는 읽기(put·delete)는 멈춘다: 정상 항목까지 빈 목록으로 덮어쓰지 않음(② §7, 2026-11-11 astra P1)
    assert division_presets.state() == {"presets": [], "broken": True}
    with pytest.raises(division_presets.Broken):
        division_presets.put("new", "셋", VALUES)
    assert (tmp_path / "p.json").read_text(encoding="utf-8") == "{broken"
    (tmp_path / "p.json").write_text(json.dumps({"version": 99, "presets": {}}), encoding="utf-8")   # 모르는 판
    assert division_presets.state()["broken"] is True
    (tmp_path / "p.json").write_text(json.dumps({"version": 1, "presets": {"p1": {"name": "좋음", "values": VALUES}, "p2": {"name": "나쁨", "values": {"stages": "x"}}}}, ensure_ascii=False), encoding="utf-8")
    assert division_presets.state()["broken"] is True   # 항목 하나가 틀려도 통째 손상 — 조용히 버리지 않는다
    with pytest.raises(division_presets.Broken):
        division_presets.delete("p1")
    (tmp_path / "p.json").unlink()
    assert division_presets.state() == {"presets": [], "broken": False}
    with pytest.raises(ValueError):   # 값 꼴 오류는 AttributeError(500)가 아니라 ValueError(400)
        division_presets.put("new", "꼴", {"stages": [1], "orgs": "bad"})


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
    assert g["profile"] == {"id": "rnd", "name": rnd.NAME, "version": rnd.VERSION, "form": "연구개발계획서", "supported": True, "supportedForms": ["연구개발계획서", "연차보고서"]}
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
    lst = c.get("/api/divisions/presets").json()
    assert [p["name"] for p in lst["presets"]] == ["시험"] and lst["broken"] is False
    view = c.get(f"/api/docs/{flow['d']}/divisions").json()
    assert view["presets"][0]["name"] == "시험" and view["presetsBroken"] is False
    assert c.put("/api/divisions/presets/new", json={"name": "꼴", "values": {"stages": [1], "orgs": "bad"}}).status_code == 400
    assert c.delete("/api/divisions/presets/p1").json() == {"deleted": "p1"} and c.delete("/api/divisions/presets/p1").status_code == 404
    path = division_presets.presets_path()   # 손상 파일 — 조회는 빈 목록 + broken, 저장·삭제는 503(고치지 않음)
    path.write_text("{broken", encoding="utf-8")
    assert c.get("/api/divisions/presets").json() == {"presets": [], "broken": True}
    assert c.get(f"/api/docs/{flow['d']}/divisions").json()["presetsBroken"] is True
    assert c.put("/api/divisions/presets/new", json={"name": "시험", "values": VALUES}).status_code == 503
    assert c.delete("/api/divisions/presets/p1").status_code == 503
    assert path.read_text(encoding="utf-8") == "{broken"
    path.unlink()


def test_plan_persists_changed_settings(flow, monkeypatch):
    """계획만 봐도 바뀐 설정이 작업(state.json)에 남는다(② §8 자동 저장 — 2026-11-11 astra P1: 전에는 「새 규칙 확인」 때만 강제 저장)."""
    monkeypatch.setenv("NFM_WORKS", str(flow["works"]))   # conftest 가 시험마다 바꾸는 작업 폴더를 픽스처 것으로
    c, d = flow["c"], flow["d"]
    values = {**VALUES, "orgs": {**VALUES["orgs"], "lead": "계획저장시험"}}
    r = c.post(f"/api/docs/{d}/divisions/plan", json={"values": values})
    assert r.status_code == 200 and r.json()["values"]["orgs"]["lead"] == "계획저장시험"
    st = json.loads((flow["works"] / d / "state.json").read_text(encoding="utf-8"))
    assert st["division"]["settings"]["values"]["orgs"]["lead"] == "계획저장시험"
    c.put(f"/api/docs/{d}/divisions/settings", json={"values": VALUES})   # 뒤 시험을 위해 되돌림


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

    def fake_ask(payload, *, call=None, effort="medium", timeout=240.0, form=None):
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

    def fake(payload, *, call_=None, effort="medium", timeout=240.0, form=None):
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


# ---------------------------------------------------------------- LLM 검토 — 두 검토를 함께 돌려 한 목록으로(② §14)

def test_review_runs_both_in_parallel_and_merges(monkeypatch):
    """`POST …/divisions/review`: 표시한 자리가 없으면 빠진 자리 검토만, 있으면 재검토와 **동시에**(두 호출이 겹쳐 떠 있음) → 재검토 반영 + 후보를 한 목록으로(같은 문단은 한 줄).
    결과는 세션·작업에 남고(GET …/divisions 의 review — 다시 열어도), auto(첫 분석)는 안 돌 까닭이 있으면 호출 없이 {skipped}, 한쪽만 답이 없으면 errors 와 함께 200, 모두 없으면 502."""
    import threading

    from app import division_llm
    server.DOCS.clear()
    c = TestClient(server.app)
    d = _open_form(c)
    call = {"backend": "fake", "model": "m", "effort": "medium", "ms": 5, "costUsd": 0.1, "error": None}
    both = threading.Barrier(2, timeout=10)   # 두 호출이 같은 때 떠 있어야 풀린다 — 차례로 부르면 시간 초과로 답 없음이 된다
    seen = {"review": 0, "missing": 0, "meet": False, "p2": None, "fail": set()}

    def fake_missing(payload, *, effort="medium", **k):
        seen["missing"] += 1
        if seen["meet"]:
            both.wait()
        if "missing" in seen["fail"]:
            return {"data": None, "prompt": "p", "call": {**call, "error": "off"}}
        p = next(p for p in payload["paragraphs"] if p["text"].startswith(MISSING_PARA))   # 「가. 기관명」 절은 이제 묶음(② §15, 2b) — 아직 묶음 밖인 문단으로
        out = [{"id": p["id"], "dim": "org", "pattern": "절: 기관마다", "reason": "기관별 계획 제목", "confidence": "medium"}]
        if any(x["id"] == seen["p2"] for x in payload["paragraphs"]):   # 재검토가 형제로 더할 문단을 빠진 자리 검토도 냄 → 한 줄로 합쳐져야
            out.append({"id": seen["p2"], "dim": "stage", "pattern": "절: 단계마다", "reason": "단계 제목 줄", "confidence": "high"})
        return {"data": {"missing": out, "summary": "빠진 곳"}, "prompt": "p", "call": call}

    def fake_review(payload, *, effort="medium", **k):
        seen["review"] += 1
        if seen["meet"]:
            both.wait()
        if "review" in seen["fail"]:
            return {"data": None, "prompt": "p", "call": {**call, "error": "off"}}
        return {"data": {"revisions": [{"action": "add", "hintId": "", "para": seen["p2"], "dim": "stage", "value": "", "reason": "형제"}], "summary": "형제 하나"},
                "prompt": "p", "call": call}
    monkeypatch.setattr(division_llm, "ask_missing", fake_missing)
    monkeypatch.setattr(division_llm, "ask", fake_review)
    # auto(첫 분석) — LLM 연결이 없으면 호출 없이
    monkeypatch.setattr(server.llm, "status", lambda: {"available": False})
    assert c.post(f"/api/docs/{d}/divisions/review", json={"auto": True}).json() == {"skipped": "llm", "review": None}
    v0 = c.get(f"/api/docs/{d}/divisions").json()
    assert v0["review"] is None and v0["reviewing"] is False and seen["missing"] == 0
    # auto — 갓 올린 문서(표시한 자리 없음): 빠진 자리 검토만
    monkeypatch.setattr(server.llm, "status", lambda: {"available": True})
    r = c.post(f"/api/docs/{d}/divisions/review", json={"auto": True})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ran"] == {"review": False, "missing": True} and out["why"] == {"review": "표시한 자리가 없습니다"} and out["errors"] == {}
    assert out["review"] is None and out["missing"]["summary"] == "빠진 곳" and out["missing"]["sent"]["paragraphs"] and out["hints"] == []
    assert [(x["kind"], x["sources"], x["confidence"]) for x in out["items"]] == [("paragraph", ["missing"], "medium")] and out["items"][0]["text"].startswith(MISSING_PARA)
    assert out["costUsd"] == 0.1 and out["detail"].startswith("divisions/review_") and (seen["review"], seen["missing"]) == (0, 1)
    v1 = c.get(f"/api/docs/{d}/divisions").json()
    assert v1["review"]["at"] == out["at"] and v1["review"]["items"] == out["items"] and "hints" not in v1["review"] and v1["reviewing"] is False
    again = c.post(f"/api/docs/{d}/divisions/review", json={"auto": True}).json()   # 이미 검토함 — 다시 부르지 않는다
    assert again["skipped"] == "done" and again["review"]["at"] == out["at"] and seen["missing"] == 1
    # 표시한 자리가 생김 — 두 검토를 동시에, 같은 문단은 한 줄
    p1, p2, _ = _three_body_paras(c, d)
    for pid, text in ((p1, "나. 1단계 계획"), (p2, "다. 2단계 추진 계획")):
        c.patch(f"/api/docs/{d}/blocks/{pid}", json={"text": text})
    c.post(f"/api/docs/{d}/divisions/hints", json={"para": p1, "dim": "stage"})
    seen.update(meet=True, p2=p2)
    r = c.post(f"/api/docs/{d}/divisions/review", json={})
    assert r.status_code == 200, r.text
    out2 = r.json()
    assert out2["ran"] == {"review": True, "missing": True} and out2["why"] == {} and out2["errors"] == {} and (seen["review"], seen["missing"]) == (1, 2)
    first = out2["items"][0]   # 재검토 줄 먼저 — 빠진 자리 검토의 꼴·확신이 붙은 한 줄
    assert first["id"] == p2 and first["sources"] == ["review", "missing"] and first["action"] == "add" and first["confidence"] == "high"
    assert first["pattern"] == "절: 단계마다" and "형제" in first["reason"] and "단계 제목 줄" in first["reason"] and first["text"] == "다. 2단계 추진 계획"
    assert [x["sources"] for x in out2["items"][1:]] == [["missing"]] and len([x for x in out2["items"] if x["id"] == p2]) == 1
    assert {h["para"]: h["by"] for h in out2["hints"]} == {p1: "user", p2: "llm"} and len(out2["review"]["applied"]) == 1
    assert out2["costUsd"] == 0.2 and out2["rev"] == c.get(f"/api/docs/{d}/divisions").json()["rev"]
    # 작업에 남는다 — 메모리에서 비우고 다시 열어도
    server.DOCS.clear()
    v2 = c.get(f"/api/docs/{d}/divisions").json()
    assert v2["review"]["at"] == out2["at"] and v2["review"]["items"] == out2["items"] and len(v2["hints"]) == 2
    # 한쪽만 답이 없으면 errors 와 함께 200, 모두 없으면 502(앞 결과는 그대로)
    seen.update(meet=False, fail={"missing"})
    out3 = c.post(f"/api/docs/{d}/divisions/review", json={}).json()
    assert out3["ran"] == {"review": True, "missing": False} and out3["errors"] == {"missing": "off"} and out3["missing"] is None
    assert [x["why"] for x in out3["review"]["skipped"]] == ["이미 표시한 문단"] and out3["items"] == []
    seen["fail"] = {"missing", "review"}
    assert c.post(f"/api/docs/{d}/divisions/review", json={}).status_code == 502
    assert c.get(f"/api/docs/{d}/divisions").json()["review"]["at"] == out3["at"]
    ev = [x for x in _log_events(c, d) if x["kind"] == "divisionReview"]
    assert [x.get("auto") for x in ev] == [True, False, False, False] and ev[1]["applied"] == 1 and ev[1]["items"] == 2 and ev[-1]["errors"]
    server.DOCS.clear()


# ---------------------------------------------------------------- 책임자 절 제목의 기관 이름 · 번호 잇기 · 양식 정보 · 값과 안 맞는 자리(② §16)

def _head_group(d, values):
    blocks = d.blocks()
    return next((g for g in rnd.find(blocks, rnd.levels_of(blocks), values) if g["dim"] == "org" and g["kind"] == "paragraph"
                 and "주관연구개발기관책임자" in g["items"][0]["labelText"]), None)


def _para_text(d, pid):
    from app.division_profiles import _structure as structure
    return " ".join(structure.index_blocks(d.blocks())[pid]["text"].split())


def test_head_section_title_gets_org_name_and_following_number():
    """7-1 「(2) 공동연구개발기관책임자」 절: 공동기관마다 한 벌이고 제목의 「책임자」 바로 뒤 괄호에 그 기관 이름(이름이 없으면 기본 이름, 주관 절에는 안 넣음, 「※」 주석은 그대로) —
    사용자 2026-11-10 "공동연구개발기관책임자 자 뒤에 (기관이름)". 묶음 뒤 같은 레벨 번호 헤딩 「(3) 참여연구자 및 연구지원인력」 은 번호를 이어 매긴다."""
    from app import hwpx_doc
    d = hwpx_doc.HwpxDoc(FORM.read_bytes())
    V = lambda joint: rnd.norm_values({"stages": [1], "orgs": {"lead": "가나", "joint": joint}})  # noqa: E731
    v = V(["다라", "", "마바"])
    g = _head_group(d, v)
    assert [it["value"] for it in g["items"]] == [("lead", 0), ("joint", None)] and len(g["tail"]) == 1 and g["plan"]["copies"] == 2
    tail = g["tail"][0]
    assert _para_text(d, tail) == "(3) 참여연구자 및 연구지원인력"
    rep = rnd.apply(d, v, levels_of=rnd.levels_of, only=g["key"])
    g = _head_group(d, v)
    labels = [" ".join(it["labelText"].split()) for it in g["items"]]
    note = " ※ 과제의 공동연구개발기관이 없을 경우 삭제"
    assert not rep["errors"] and rep["added"] == 2 and g["plan"]["done"] and g["tail"] == [tail]
    assert labels == ["(1) 주관연구개발기관책임자", "(2) 공동연구개발기관책임자(다라)" + note, "(3) 공동연구개발기관책임자(참여기관2)" + note, "(4) 공동연구개발기관책임자(마바)" + note]
    assert _para_text(d, tail) == "(5) 참여연구자 및 연구지원인력"
    # 이름을 넣은 뒤에도 같은 묶음 — 기관을 더하면 한 벌 더, 이름을 바꾼 값(라벨에 값에 없는 이름)이면 그대로(지원 안 됨)
    more = _head_group(d, V(["다라", "", "마바", "사아"]))
    assert len(more["target"]) == 5 and more["plan"]["copies"] == 1 and not more["plan"]["drop"] and not more["irregular"]
    renamed = _head_group(d, V(["다라", "", "다른이름"]))
    assert renamed["irregular"] and renamed["target"] is None and renamed["plan"] is None
    # 긴 기관 이름도 라벨로 남는다(이름 괄호는 라벨 길이에 안 셈)
    long_name = "한국해양과학기술원 부설 선박해양플랜트연구소 해양시스템연구본부"
    assert rnd.core._label(f"  (2) 공동연구개발기관책임자({long_name})   ※ 주석")[2] == rnd.core._label("  (1) 주관연구개발기관책임자")[2]
    # 이 규칙 전에 반영한 문서(묶음 수는 맞는데 뒤 번호가 어긋남) — 그 묶음이 다시 바꿀 자리가 되고 번호만 고친다
    d.set_text(tail, " (3) 참여연구자 및 연구지원인력")
    g = _head_group(d, v)
    assert not g["plan"]["done"] and not g["plan"]["copies"] and not g["plan"]["drop"]
    rep = rnd.apply(d, v, levels_of=rnd.levels_of, only=g["key"])
    assert [(c["id"], " ".join(c["new"].split())) for c in rep["changes"]] == [(tail, "(5) 참여연구자 및 연구지원인력")] and not rep["added"] and not rep["removed"]
    # 이름을 넣은 뒤 기관을 뺀 값이면 라벨에 「값에 없는 이름」 이 남아 그대로(② §15 와 같은 보호 — 「이번 반영 취소」 뒤 다시 반영)
    assert _head_group(d, V([]))["target"] is None
    # 빈 양식에서 공동기관 0곳 — 그 절을 지우고 뒤 번호는 (2)
    d = hwpx_doc.HwpxDoc(FORM.read_bytes())
    v0 = V([])
    g = _head_group(d, v0)
    assert g["target"] == [("lead", 0)] and g["plan"]["drop"] == [1]
    rep = rnd.apply(d, v0, levels_of=rnd.levels_of, only=g["key"])
    assert not rep["errors"] and rep["removed"] == 1 and _head_group(d, v0) is None and _para_text(d, tail) == "(2) 참여연구자 및 연구지원인력"


def test_tail_numbers_stop_at_other_labels():
    """번호 잇기는 묶음 뒤 **같은 레벨 번호 헤딩**만 — 다른 묶음의 라벨(「[2단계]」 아래 「(1) 1차년도」)·더 얕은 헤딩 앞에서 멈춘다: 빈 양식에서 뒤 번호를 갖는 묶음은 책임자 절 하나."""
    from app import hwpx_doc
    blocks = hwpx_doc.HwpxDoc(FORM.read_bytes()).blocks()
    groups = rnd.find(blocks, rnd.levels_of(blocks), rnd.norm_values(VALUES))
    tailed = [g for g in groups if g.get("tail")]
    assert len(tailed) == 1 and "주관연구개발기관책임자" in tailed[0]["items"][0]["labelText"]
    assert any(g["dim"] == "year" and g["kind"] == "paragraph" and g["items"][0]["labelText"].strip().startswith("(1)") and g["tail"] == [] for g in groups)


FORM_INFO = """# 양식 정보 — 시험

```json
{"name": "시험 계획서", "match": {"names": ["*연구개발계획서*"]}}
```

<!-- 사람만 보는 메모 DIVMEMO -->

## 구분 기준 자리 — 값마다 늘리고 줄이는 곳
- 책임자 절은 공동기관마다 한 벌 DIVFACT.
"""


def test_review_sends_form_info_and_reports_pending(monkeypatch, tmp_path):
    """양식마다 관리하는 요청(양식 정보 — forms/<키>.md)이 구분 기준 LLM 검토 프롬프트에 한 절로 붙고(계약 뒤·자료 앞, 조건 블록·주석은 빼고) 결과에 어느 양식 글이 갔는지 남는다.
    검토 결과에는 스크립트가 센 「값과 아직 안 맞는 묶음」(pending)도 — 구분 값을 안 넣었으면 null. 맞는 양식이 없으면 프롬프트는 전과 같다."""
    import os

    from app import division_llm, llm
    forms = Path(os.environ["NFM_FORMS"])
    forms.mkdir(parents=True, exist_ok=True)
    (forms / "시험계획서.md").write_text(FORM_INFO, encoding="utf-8")
    seen = []

    def fake_call(schema, content, what, *, timeout=180.0, effort=None, model=None):
        seen.append((what, content))
        data = {"missing": [], "summary": "없음"} if what == "divisions-missing" else {"revisions": [], "summary": "없음"}
        return {"data": data, "backend": "fake", "model": "m", "effort": effort, "ms": 1, "costUsd": 0, "error": None}
    monkeypatch.setattr(llm, "call", fake_call)
    server.DOCS.clear()
    c = TestClient(server.app)
    d = _open_form(c)
    v0 = c.get(f"/api/docs/{d}/divisions").json()
    assert v0["formInfo"] == {"key": "시험계획서", "name": "시험 계획서", "how": "name"}
    out = c.post(f"/api/docs/{d}/divisions/review", json={}).json()
    what, prompt = seen[-1]
    head = "## 양식 정보 — 시험 계획서 (이 양식에만 해당)"
    assert what == "divisions-missing" and prompt.startswith(division_llm.MISSING_CONTRACT + "\n\n" + head) and prompt.count("## 자료(JSON)") == 1
    assert prompt.index(head) < prompt.index("DIVFACT") < prompt.index("## 자료(JSON)") and "DIVMEMO" not in prompt and "```json" not in prompt
    assert out["form"]["key"] == "시험계획서" and out["form"]["name"] == "시험 계획서" and len(out["form"]["sha1"]) == 40
    assert out["pending"] is None   # 구분 값을 아직 안 넣음
    # 값을 넣으면 스크립트가 센 「값과 안 맞는 묶음」 이 결과에(작업에도 남는다) — 빈 양식이라 책임자 절을 포함해 여럿
    assert c.put(f"/api/docs/{d}/divisions/settings", json={"values": VALUES}).status_code == 200
    out2 = c.post(f"/api/docs/{d}/divisions/review", json={}).json()
    pend = out2["pending"]
    assert len(pend) > 20 and {"key", "dim", "dimName", "kind", "kindName", "labels", "count", "target"} <= set(pend[0])
    head_p = next(p for p in pend if p["labels"][0].startswith("(1) 주관연구개발기관책임자"))
    assert head_p["dimName"] == "기관" and head_p["kindName"] == "문단 묶음" and (head_p["count"], head_p["target"]) == (2, 3)
    assert c.get(f"/api/docs/{d}/divisions").json()["review"]["pending"] == pend
    # 낱개 끝점도 같은 양식 글을 보낸다
    r = c.post(f"/api/docs/{d}/divisions/llm_missing", json={}).json()
    assert r["form"]["key"] == "시험계획서" and "DIVFACT" in seen[-1][1]
    # 맞는 양식이 없으면(다른 조건) 절이 없고 프롬프트는 계약 + 자료
    (forms / "시험계획서.md").write_text(FORM_INFO.replace("*연구개발계획서*", "*다른문서*"), encoding="utf-8")
    assert c.get(f"/api/docs/{d}/divisions").json()["formInfo"] is None
    r = c.post(f"/api/docs/{d}/divisions/llm_missing", json={}).json()
    assert r["form"] is None and seen[-1][1].startswith(division_llm.MISSING_CONTRACT + "\n\n## 자료(JSON)\n") and "양식 정보" not in seen[-1][1].split("## 자료(JSON)")[0].replace(division_llm.MISSING_CONTRACT, "")
    assert division_llm.form_part(None) == "" and division_llm.form_part({"key": "k", "name": "n", "text": "# 제목\n\n## 절\n-\n"}) == ""   # 손대지 않은 뼈대 = 보낼 글 없음
    # 머리 문장은 검토마다 다르다 — 재검토는 답이 곧 추가한 자리에 반영되므로 「형제만」(양식 정보에 적힌 자리라고 새로 더하지 않음)
    form = {"key": "k", "name": "n", "sha1": "s", "text": FORM_INFO}
    p_missing, p_review = division_llm.ask_missing({"x": 1}, form=form)["prompt"], division_llm.ask({"x": 1}, form=form)["prompt"]
    assert division_llm.FORM_NOTE in p_missing and division_llm.FORM_NOTE_REVIEW not in p_missing
    assert division_llm.FORM_NOTE_REVIEW in p_review and division_llm.FORM_NOTE not in p_review and p_review.startswith(division_llm.CONTRACT + "\n\n## 양식 정보 — n")
    server.DOCS.clear()


def test_comment_is_appended_to_the_form_info(monkeypatch):
    """양식별 코멘트(② §18): 맞는 양식이 없으면 프로파일이 판정한 양식 이름(없으면 파일 이름에서 낸 키)으로 코멘트만 든 파일을 만들어 이 문서의 양식으로 고르고,
    있으면 그 파일의 「구분 기준 자리」 절 코멘트 목록 끝에 붙인다. 세션 상태(rev·계획·추가한 자리·설정)는 그대로 · 빈 글·500자 넘음 400 · 저장 끔 503 ·
    그 사이 고쳐진 글은 한 번 다시 읽어 붙임. 코멘트는 양식 글과 함께 검토 프롬프트에 간다."""
    import os
    import time

    from app import division_llm
    from app import heading_forms as F
    forms = Path(os.environ["NFM_FORMS"])
    server.DOCS.clear()
    c = TestClient(server.app)
    d = _open_form(c)
    url = f"/api/docs/{d}/divisions/comments"
    v0 = c.get(f"/api/docs/{d}/divisions").json()
    assert v0["formInfo"] is None and v0["comments"] == [] and v0["profile"]["form"] == "연구개발계획서"
    assert [c.post(url, json=b).status_code for b in ({"text": " \n "}, {"text": "가" * 501}, {})] == [400, 400, 400]
    assert not list(forms.glob("*.md"))
    today = time.strftime("%Y-%m-%d")
    r = c.post(url, json={"text": " 책임자 절은\n기관마다\t한 벌 "})
    assert r.status_code == 200, r.text
    out = r.json()
    first = {"date": today, "text": "책임자 절은 기관마다 한 벌"}
    assert out == {"formInfo": {"key": "연구개발계획서", "name": "연구개발계획서", "how": "manual"}, "comments": [first], "created": True}
    text = (forms / "연구개발계획서.md").read_text("utf-8")
    assert F.parse(text) == {"name": "연구개발계획서", "names": ["*연구개발계획서*"], "sha256": [F.doc_sha(server._sess(d))]}
    assert text.count("## ") == 1 and "<!--" not in text   # 빈 뼈대 절 없음 — 제목 · 조건 블록 · 「구분 기준 자리」 절뿐
    assert text.endswith(f"\n```\n\n## {F.DIVISION_TITLE}\n\n{F.COMMENT_HEAD}\n- ({today}) 책임자 절은 기관마다 한 벌\n")
    assert F.choice(d) == "연구개발계획서" and F.pin(server._sess(d))["how"] == "manual"
    v1 = c.get(f"/api/docs/{d}/divisions").json()
    assert v1["formInfo"] == out["formInfo"] and v1["comments"] == [first]
    assert all(v1[k] == v0[k] for k in ("rev", "plan", "hints", "settings", "applied", "stale"))   # 세션 상태는 그대로
    # 둘째 — 같은 파일의 목록 끝에(머리 줄은 하나). 고른 것을 풀어도 sha256 조건으로 맞고, 맞은 양식은 다시 고르지 않는다
    F.set_choice(d, None)
    out2 = c.post(url, json={"text": "둘째 COMMENTFACT"}).json()
    assert out2["created"] is False and out2["formInfo"]["how"] == "sha256" and [x["text"] for x in out2["comments"]] == [first["text"], "둘째 COMMENTFACT"]
    assert F.choice(d) is None and (forms / "연구개발계획서.md").read_text("utf-8").count(F.COMMENT_HEAD) == 1
    part = division_llm.form_part(server._division_form(server._sess(d)))
    assert "COMMENTFACT" in part and "「코멘트」" in division_llm.FORM_NOTE and "「코멘트」" in division_llm.FORM_NOTE_REVIEW
    # 읽은 뒤 다른 곳에서 고쳐 sha 가 어긋남 → 한 번 다시 읽어 붙인다, 또 어긋나면 503(파일은 그대로)
    real, calls = F.pin, []

    def stale_once(sess):
        calls.append(1)
        return {**real(sess), "sha1": "0" * 40} if len(calls) == 1 else real(sess)
    monkeypatch.setattr(F, "pin", stale_once)
    out3 = c.post(url, json={"text": "셋째"}).json()
    assert len(calls) == 2 and [x["text"] for x in out3["comments"]][2:] == ["셋째"]
    monkeypatch.setattr(F, "pin", lambda sess: {**real(sess), "sha1": "0" * 40})
    assert c.post(url, json={"text": "넷째"}).status_code == 503
    monkeypatch.setattr(F, "pin", real)
    assert len(c.get(f"/api/docs/{d}/divisions").json()["comments"]) == 3
    # 같은 키의 파일이 있는데 조건이 안 맞음 → 그 파일에 붙이고(만들지 않음) 이 문서의 양식으로 고른다 — 절은 있고 머리 줄이 없으면 절 끝에 머리 줄부터
    (forms / "연구개발계획서.md").write_text(FORM_INFO.replace("*연구개발계획서*", "*다른문서*"), encoding="utf-8")
    assert c.get(f"/api/docs/{d}/divisions").json()["formInfo"] is None
    out4 = c.post(url, json={"text": "있던 파일에"}).json()
    assert out4 == {"formInfo": {"key": "연구개발계획서", "name": "시험 계획서", "how": "manual"}, "comments": [{"date": today, "text": "있던 파일에"}], "created": False}
    assert f"DIVFACT.\n\n{F.COMMENT_HEAD}\n- ({today}) 있던 파일에\n" in (forms / "연구개발계획서.md").read_text("utf-8") and F.choice(d) == "연구개발계획서"
    # 프로파일이 양식을 못 알아본 문서 — 파일 이름에서 낸 키(heading_forms.suggest)
    d2 = c.post("/api/docs", files={"file": (SMALL.name, SMALL.read_bytes())}).json()["docId"]
    assert c.get(f"/api/docs/{d2}/divisions").json()["profile"]["form"] is None
    out5 = c.post(f"/api/docs/{d2}/divisions/comments", json={"text": "작은 문서"}).json()
    assert out5["created"] is True and out5["formInfo"] == {"key": "기술수요조사서", "name": "기술수요조사서", "how": "manual"}
    assert (forms / "기술수요조사서.md").read_text("utf-8").count("## ") == 1
    # 양식 정보 저장 끔 → 503, 조회는 빈 목록
    monkeypatch.setenv("NFM_FORMS", "off")
    assert c.post(url, json={"text": "꺼짐"}).status_code == 503
    v9 = c.get(f"/api/docs/{d}/divisions").json()
    assert v9["formInfo"] is None and v9["comments"] == []
    server.DOCS.clear()


def test_tail_is_left_alone_when_the_number_chain_resumes_after_a_break():
    """번호 잇기(② §16)의 경계: 절 제목·더 얕은 헤딩 앞까지, 더 깊은 헤딩·본문은 건너뜀. 구분 라벨이나 다른 꼴의 같은 레벨 헤딩으로 끊긴 뒤 같은 번호 사슬이 또 나오면
    앞쪽만 고쳐 번호가 겹치게 되므로 아예 건드리지 않는다. 뒤 헤딩들의 번호가 저희끼리 차례가 아니어도 그대로."""
    core = rnd.core
    P = lambda i, t: {"id": f"p{i}", "type": "paragraph", "text": t}  # noqa: E731
    head = [P(0, "(1) 주관연구개발기관책임자"), P(1, "o"), P(2, "(2) 공동연구개발기관책임자"), P(3, "o"), P(4, "(3) 참여연구자")]
    rest = [P(5, "가. 현황"), P(6, "(4) 그 밖"), P(7, "8-1. 다음 절"), P(8, "(5) 다른 절의 것")]
    levels = {"p0": 3, "p2": 3, "p4": 3, "p5": 4, "p6": 3, "p7": 2, "p8": 3, "p11": 3}
    labs = [head[0], head[2]]
    assert core._tail(head + rest, 3, labs, levels) == ["p4", "p6"]
    assert core._tail(head + [P(9, "[1단계]")] + rest, 3, labs, levels) == []                    # 구분 라벨 뒤에 「(4)」 가 이어짐
    assert core._tail(head + [P(9, "[1단계]"), P(10, "o")] + rest[2:], 3, labs, levels) == ["p4"]   # 끊긴 뒤 같은 사슬이 없으면 앞쪽만
    assert core._tail(head + [P(11, "□ 번호 없는 같은 레벨 헤딩")] + rest, 3, labs, levels) == []
    assert core._tail(head + [P(6, "(5) 건너뛴 번호")], 3, labs, levels) == []                    # (3), (5) — 저희끼리 차례가 아님
    assert core._tail(head[2:], 1, [head[2]], levels) == []                                       # 묶음 라벨이 1부터가 아님


def test_plan_with_nothing_to_do_confirms_the_current_rules():
    """옛 프로파일 판으로 반영한 문서(화면 「새 규칙 — 계획 확인」): 지금 규칙으로 전체 계획을 세웠는데 할 일이 없으면 마지막 반영의 판을 지금 판으로 올린다(표시가 꺼짐, 작업에도 남음).
    자리를 뺀 계획은 확인으로 치지 않는다."""
    server.DOCS.clear()
    c = TestClient(server.app)
    d = _open_form(c)
    assert c.put(f"/api/docs/{d}/divisions/settings", json={"values": {"stages": [1], "orgs": {"lead": "가나", "joint": []}}}).status_code == 200
    plan = c.post(f"/api/docs/{d}/divisions/plan", json={}).json()
    assert c.post(f"/api/docs/{d}/divisions/apply", json={"planId": plan["planId"]}).status_code == 200
    version = lambda: c.get(f"/api/docs/{d}/divisions").json()["applied"]["profileVersion"]  # noqa: E731
    assert version() == rnd.VERSION
    server._sess(d).division["applied"]["profileVersion"] = rnd.VERSION - 1   # 옛 판으로 반영한 것처럼
    assert c.post(f"/api/docs/{d}/divisions/plan", json={"skip": ["period"]}).status_code == 200 and version() == rnd.VERSION - 1
    again = c.post(f"/api/docs/{d}/divisions/plan", json={}).json()
    assert again["summary"]["applied"] == 0 and not again["changes"] and version() == rnd.VERSION
    server.DOCS.clear()
    assert version() == rnd.VERSION   # 메모리에서 비우고 다시 열어도
    server.DOCS.clear()


def test_apply_names_the_frame():
    """프레임 이름(spec_작업 ② §10 — 2026-11-14 사용자 "프로젝트 구성 반영이 완료 하면 사업계획서_{프로젝트이름}_프레임 .. 이라고 파일명을 저장하도록"): 양식 맞추기 TASK 의 문서에
    프로젝트 구성을 반영하면(계획 → 반영 끝점) 문서·작업 목록·내려받는 이름이 「사업계획서_<프로젝트>_프레임.hwpx」, 그 반영을 실행 취소하면 올린 이름으로 돌아온다. 저장된 이름은 그대로."""
    from urllib.parse import quote
    from app import works
    server.DOCS.clear()
    c = TestClient(server.app)
    d = _open_form(c)
    assert c.put(f"/api/works/{d}/task", json={"kind": "rnd", "file": "plan", "job": "plan_fit", "project": "프레임 과제"}).status_code == 200
    assert c.put(f"/api/docs/{d}/divisions/settings", json={"values": {"stages": [1], "orgs": {"lead": "가나", "joint": []}}}).status_code == 200
    names = lambda: (c.get(f"/api/docs/{d}").json()["name"], next(w for w in c.get("/api/works").json() if w["id"] == d)["name"])  # noqa: E731
    assert names() == (FORM.name, FORM.name)   # 반영 전
    plan = c.post(f"/api/docs/{d}/divisions/plan", json={}).json()
    assert names() == (FORM.name, FORM.name)   # 계획만으로는 안 바뀐다
    done = c.post(f"/api/docs/{d}/divisions/apply", json={"planId": plan["planId"]})
    assert done.status_code == 200 and done.json().get("applied")
    frame = "사업계획서_프레임 과제_프레임.hwpx"
    assert names() == (frame, frame) and works.work(d)["name"] == FORM.name
    cd = c.get(f"/api/docs/{d}/download").headers["content-disposition"]
    assert quote(frame) in cd and quote("_수정") not in cd
    server._persist_all()
    assert works.work(d)["framed"] is True
    assert c.post(f"/api/docs/{d}/undo").json()["name"] == FORM.name and names() == (FORM.name, FORM.name)   # 그 반영을 실행 취소
    server._persist_all()
    assert works.work(d)["framed"] is False
    server.DOCS.clear()


# ---------------------------------------------------------------- 서명 줄 맞춤(② §20)

REPORT = FORM.parent / "국가RnD_서식" / "KEIT_표준서식_260320" / "1. 산업기술혁신사업 연차보고서 서식_260319.hwpx"


def _sign_lines(d):
    """표지의 서명 줄 「…연구개발기관(이름)의 장:   (직인)」 — [(문단 id, 글, 「(직인)」 앞 빈칸 수, 「(직인)」 자리 = 그 앞 글의 폭 pt, 빈칸 하나 폭 pt)].
    폭은 엔진의 자(core._sign_width — 글꼴 글자 폭 × 장평 × 자간 × 크기)로 잰다."""
    from app.division_profiles import _structure as structure
    core, out = rnd.core, []
    for b in structure.iter_blocks(d.blocks()):
        m = core.SIGN_LINE.match(b.get("text") or "") if b.get("type") == "paragraph" else None
        if m:
            fmt = core._sign_fmt(b, m.end(1) - 1)
            out.append((b["id"], b["text"], len(m.group(2)), core._sign_width(m.group(1) + m.group(2), fmt), core._sign_width(" ", fmt)))
    return out


def _sign_gaps(d):
    """서명 줄마다 「(직인)」 앞 빈칸 수 — 「(직인)」 자리가 줄마다 같은지도 본다: 빈칸이 가장 적은 줄(가장 넓은 줄 — 기준)에서 빈칸 반 칸 안쪽."""
    lines = _sign_lines(d)
    ref = min(lines, key=lambda x: x[2])[3]
    assert all(abs(x - ref) <= s / 2 + 1e-6 for *_, x, s in lines), lines
    return [n for _, _, n, _, _ in lines]


def _sign_group(d, v, prior=None):
    blocks = d.blocks()
    return next(g for g in rnd.find(blocks, rnd.levels_of(blocks), v, prior=prior)
                if g["dim"] == "org" and g["kind"] == "paragraph" and rnd.core.SIGN_LINE.match(g["items"][0]["labelText"]))


@pytest.mark.parametrize("form", [REPORT, FORM], ids=["report", "plan"])
def test_sign_lines_carry_no_org_name(form):
    """서명 줄에는 기관 이름을 넣지 않는다(② §20, 사용자 2026-11-12 "여기 기관은 안들어 가는거 같아" — 물어서 받은 답 「이름만 뺌」): 표지 「주관연구개발기관의 장:      (직인)」 줄은
    기관 수만큼 줄만 늘고 글은 서식 그대로다 — 이름 괄호가 없으니 「(직인)」 이 양식의 15칸으로 저절로 한 줄에 선다. 다시 계획하면 할 일 없음 · 이름만 바꾼 값이면 서명 줄은
    바꿀 것이 없음 · 기관을 빼면 줄만 줆 · 옛 판(프로파일 판 7 까지)이 이름을 넣고 빈칸을 늘린 문서는 이름 괄호를 빼고 빈칸을 15칸으로 되돌림 · 「연구책임자: (서명)」 줄은 그대로."""
    if not form.exists():
        pytest.skip("KEIT 연차보고서 서식 hwpx 없음")
    from app import hwpx_doc
    from app.division_profiles import _structure as structure
    d = hwpx_doc.HwpxDoc(form.read_bytes())
    V = lambda lead, joint: rnd.norm_values({"stages": [1], "orgs": {"lead": lead, "joint": joint}})  # noqa: E731
    signer = lambda: [b["text"] for b in structure.iter_blocks(d.blocks()) if b.get("type") == "paragraph" and "(서명)" in b["text"]]  # noqa: E731
    heads = lambda: [t.split("의 장")[0] for _, t, *_ in _sign_lines(d)]  # noqa: E731
    v1 = V("한국선급", ["씨드로닉스", "유엔젤", "랩오투원"])
    g = _sign_group(d, v1)
    signer0 = signer()
    assert [n for _, _, n, _, _ in _sign_lines(d)] == [15, 15] and not g["plan"]["done"] and (form != REPORT or len(signer0) == 1)
    rep = rnd.apply(d, v1, levels_of=rnd.levels_of, only=g["key"])
    assert not rep["errors"] and rep["added"] == 2
    assert heads() == ["주관연구개발기관", "공동연구개발기관", "공동연구개발기관", "공동연구개발기관"]   # 줄만 기관 수만큼 — 이름 괄호 없음
    assert _sign_gaps(d) == [15, 15, 15, 15]   # 글이 서식 그대로라 양식의 15칸으로 「(직인)」 이 한 줄에 선다
    # 같은 값으로 다시 계획 — 할 일 없음
    assert _sign_group(d, v1, [v1])["plan"]["done"]
    rep = rnd.apply(d, v1, levels_of=rnd.levels_of, only=g["key"], prior=[v1])
    assert rep["passes"] == 0 and not rep["changes"]
    # 이름만 바꾼 값 — 서명 줄에는 이름이 없어 바꿀 것이 없다
    v2 = V("KR", ["씨드", "LG이노텍", "유엔젤"])
    assert _sign_group(d, v2, [v1])["plan"]["done"]
    # 기관을 뺀 값 — 줄만 준다
    v3 = V("KR", ["유엔젤"])
    g = _sign_group(d, v3, [v1, v2])
    rep = rnd.apply(d, v3, levels_of=rnd.levels_of, only=g["key"], prior=[v1, v2])
    assert not rep["errors"] and rep["removed"] == 2 and heads() == ["주관연구개발기관", "공동연구개발기관"] and _sign_gaps(d) == [15, 15]
    # 옛 판이 반영한 문서(이름 괄호 + 이름 길이에 맞춰 늘린 빈칸) — 그 묶음이 다시 바꿀 자리가 되고, 이름 괄호를 빼고 빈칸을 15칸으로 되돌린다
    plain = _sign_lines(d)
    for (pid, text, *_), (name, n) in zip(plain, [("KR", 21), ("유엔젤", 15)]):
        d.set_text(pid, rnd.core.SIGN_LINE.sub(lambda m: m.group(1).replace("연구개발기관의", f"연구개발기관({name})의") + " " * n + m.group(3), text))  # noqa: B023
    assert heads() == ["주관연구개발기관(KR)", "공동연구개발기관(유엔젤)"]
    g = _sign_group(d, v3, [v1, v2, v3])
    assert not g["plan"]["done"] and not g["plan"]["copies"] and not g["plan"]["drop"]
    rep = rnd.apply(d, v3, levels_of=rnd.levels_of, only=g["key"], prior=[v1, v2, v3])
    assert not rep["errors"] and sorted((c["id"], c["new"]) for c in rep["changes"]) == sorted((pid, text) for pid, text, *_ in plain)
    assert _sign_group(d, v3, [v1, v2, v3])["plan"]["done"]
    assert signer() == signer0   # 「연구책임자: (서명)」 줄은 안 건드린다


def test_sign_lines_with_entrust_lines_and_written_lines():
    """맞닿은 위탁 서명 줄(따로 묶음 — 혁신법 별지 1 서식)도 주관·공동 줄처럼 이름 없이 줄만 는다. 쌍점과 「(직인)」 사이에 기관장 이름을 쓴 줄은 쓴 글(이름·빈칸)을
    그대로 둔다 — 옛 판이 넣은 기관 이름 괄호만 그 줄에서도 뺀다. docx(글꼴의 빈칸 폭 그대로)로도 같은 규칙."""
    import io

    import docx
    from app.docx_doc import DocxDoc
    src = docx.Document()
    for t in ["연구책임자:                (서명)", "주관연구개발기관의 장:               (직인)", "공동연구개발기관의 장:               (직인)",
              "위탁연구개발기관의 장:               (직인)", "", "산업통상부 장관 귀하"]:
        src.add_paragraph(t)
    buf = io.BytesIO()
    src.save(buf)
    d = DocxDoc(buf.getvalue())
    V = lambda joint: rnd.norm_values({"stages": [1], "orgs": {"lead": "한국선급", "joint": joint, "entrust": ["위탁하나", "가"]}})  # noqa: E731
    v = V(["씨드로닉스", "KR"])
    rep = rnd.apply(d, v)
    assert not rep["errors"] and rep["added"] == 2
    lines = _sign_lines(d)
    assert [t.split("의 장")[0] for _, t, *_ in lines] == ["주관연구개발기관", "공동연구개발기관", "공동연구개발기관", "위탁연구개발기관", "위탁연구개발기관"]
    assert _sign_gaps(d) == [15] * 5   # 두 묶음의 다섯 줄이 이름 없이 한 자리
    assert not rnd.apply(d, v, prior=[v])["changes"]
    # 주관 줄에 기관장 이름을 쓴 뒤 공동 이름을 바꾼 값 — 쓴 줄은 그대로, 나머지 줄도 바꿀 것이 없다(서명 줄에 이름이 없다)
    pid = lines[0][0]
    text_of = lambda: next(b["text"] for b in d.blocks() if b["id"] == pid)  # noqa: E731
    written = "주관연구개발기관의 장:    이영석     (직인)"
    d.set_text(pid, written)
    v2 = V(["씨드", "KR"])
    rep = rnd.apply(d, v2, prior=[v])
    assert not rep["errors"] and not rep["changes"] and text_of() == written and pid not in [x[0] for x in _sign_lines(d)]
    # 옛 판이 기관 이름을 넣은 줄에 기관장 이름을 쓴 문서 — 사람이 쓴 줄은 꼴이 달라 묶음 밖이라 통째로 그대로(기관 이름 괄호도). 옛 판이 이름을 넣은 위탁 줄은 괄호가 빠진다
    written = "주관연구개발기관(한국선급)의 장:    이영석     (직인)"
    d.set_text(pid, written)
    eid, etext = _sign_lines(d)[-1][:2]
    d.set_text(eid, etext.replace("위탁연구개발기관의", "위탁연구개발기관(가)의"))
    rep = rnd.apply(d, v2, prior=[v])
    assert not rep["errors"] and text_of() == written and [(c["id"], c["new"]) for c in rep["changes"]] == [(eid, etext)]
    assert _sign_gaps(d) == [15] * 4


def test_sign_lines_beside_untouched_lines():
    """계획이 없는 묶음(값에 없는 이름이 적힌 — 작성한 문서)의 서명 줄은 안 건드리고, 맞닿은 위탁 줄은 그 줄들의 지금 「(직인)」 자리에 맞춘다(빈칸 반 칸 안쪽)."""
    core = rnd.core
    P = lambda i, t: {"id": f"p{i}", "type": "paragraph", "text": t}  # noqa: E731
    blocks = [P(0, "주관연구개발기관(남의이름)의 장:     (직인)"), P(1, "공동연구개발기관(다른이름이길다)의 장:        (직인)"), P(2, "위탁연구개발기관의 장:     (직인)")]
    v = rnd.norm_values({"stages": [1], "orgs": {"lead": "가", "joint": ["나"], "entrust": ["위탁"]}})
    named, entrust = core.find(blocks, {}, v, prior=[])
    assert named["named"] and named["plan"] is None and "sign" not in named
    w = lambda t: core._sign_width(t, {})  # noqa: E731
    want = w("공동연구개발기관(다른이름이길다)의 장:" + " " * 8)   # 안 건드리는 줄 가운데 「(직인)」 이 가장 오른쪽인 자리
    n = entrust["sign"][0]
    assert not entrust["plan"]["done"] and abs(w("위탁연구개발기관의 장:" + " " * n) - want) <= w(" ") / 2 + 1e-6   # 위탁 줄에도 이름은 안 넣는다 — 빈칸만 그 자리로
    assert core._changes(entrust, v, entrust["items"][0], 1, 1, ("entrust", 1), {b["id"]: b for b in blocks}) == [("p2", "위탁연구개발기관의 장:" + " " * n + "(직인)")]


def test_sign_lines_ignore_long_org_names():
    """긴 기관 이름도 서명 줄을 밀지 않는다(이름을 안 넣으므로 — 전에는 이름이 길면 「(직인)」 이 다음 줄로 넘어가 그 줄을 맞춤에서 뺐다). 옛 판이 긴 이름을 넣어 둔 줄
    (빈칸 뺀 글이 LABEL_MAX 를 넘는 24자 이름 — 전에는 라벨에서 빠져 다시 반영이 멈췄다)도 서명 줄로 찾아 이름 괄호를 뺀다."""
    from app import hwpx_doc
    d = hwpx_doc.HwpxDoc(FORM.read_bytes())
    long = "한국조선해양기자재연구원부산본원시험인증센터지부"
    v = rnd.norm_values({"stages": [1], "orgs": {"lead": "한국선급", "joint": [long, "유엔젤", "랩오투원"]}})
    g = _sign_group(d, v)
    rep = rnd.apply(d, v, levels_of=rnd.levels_of, only=g["key"])
    assert not rep["errors"] and [n for _, _, n, _, _ in _sign_lines(d)] == [15, 15, 15, 15]
    assert _sign_group(d, v, [v])["plan"]["done"] and not rnd.apply(d, v, levels_of=rnd.levels_of, only=g["key"], prior=[v])["changes"]
    pid, text = _sign_lines(d)[1][:2]
    d.set_text(pid, text.replace("연구개발기관의", f"연구개발기관({long})의"))
    g = _sign_group(d, v, [v])
    assert len(g["items"]) == 4 and not g["plan"]["done"]
    rep = rnd.apply(d, v, levels_of=rnd.levels_of, only=g["key"], prior=[v])
    assert not rep["errors"] and [(c["id"], c["new"]) for c in rep["changes"]] == [(pid, text)] and _sign_group(d, v, [v])["plan"]["done"]

