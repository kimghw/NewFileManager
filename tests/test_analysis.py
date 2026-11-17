"""분석 상태(spec_작업 ② §20 — app/analysis.py · app/analysis_api.py): 문서마다 헤딩 · 표(스크립트) · LLM 판정 · 구분 기준 LLM 검토(옵션)가 어디까지 됐는지를 같은 꼴로.
읽기만 하는지(분석을 시작하지 않음) · 도는 작업의 차례(첫 분석 = 헤딩 → 표) · LLM 은 지금 결과 기준 · 문서를 고쳐도 done(뼈대 유지) · 해당 없는 항목은 없음(docx · 지원 양식 아님)."""
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import analysis, heading_runs, server

SAMPLES = Path(__file__).parents[1] / "samples"
SMALL, DOCX, FORM = SAMPLES / "기술수요조사서.hwpx", SAMPLES / "기술수요조사서.docx", SAMPLES / "연구개발계획서_양식.hwpx"


@pytest.fixture
def client():
    server.DOCS.clear()
    return TestClient(server.app)


def _upload(c, path=SMALL):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _wait_heads(c, d, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        v = c.get(f"/api/docs/{d}/headings").json()
        if v["job"] and v["job"]["status"] != "running":
            return v
        time.sleep(0.05)
    raise AssertionError("헤딩 추출이 끝나지 않음")


def _items(v):
    return {i["key"]: i for i in v["items"]}


FOUR = ["heads", "templates", "formats", "tables"]   # 항목 차례(② §20 「넷」) — 구분 기준은 그 뒤 옵션


def _base2(v):
    """헤딩 · 표 — 기본 분석(스크립트) 두 항목만(템플릿 · 서식은 헤딩 그래프에 기댄 셈)."""
    return [i for i in v["items"] if i["key"] in ("heads", "tables")]


def _paras(blocks):
    """문단 블록을 문서 차례로(표 칸 안까지)."""
    out = []
    for b in blocks:
        if "text" in b:
            out.append(b)
        for c in b.get("cells", ()):
            out += _paras(c["blocks"])
    return out


# ---------------------------------------------------------------- 셈(가짜 세션 — 빠름)

def _sess(st, rev=3, fmt="hwpx", division=None):
    return SimpleNamespace(id="x", rev=rev, fmt=fmt, heads={"loaded": True, "runs": [], "job": None, "stage1": None, "stage2": None, "stage3": None, **st}, division=division or {})


def _job(stage=3, llm=False, first=False, status="running", error=None):
    j = heading_runs.Job(stage, llm, 3)
    j.first, j.status, j.error = first, status, error
    return j


def _res(run, rev=3, llm=None, **counts):
    return {"meta": {"run": run, "rev": rev, "at": 100.0 + run}, "counts": counts, "llm": {"requested": False, "fallback": True, "error": None, **(llm or {})}}


def test_states_are_the_documented_ones_and_nothing_means_none():
    v = analysis.status(_sess({}))
    assert v["base"] == "none" and v["job"] is None and [i["key"] for i in v["items"]] == FOUR
    for i in _base2(v):
        assert i["state"] == "none" and i["llm"]["state"] == "none" and i["run"] is None and i["moved"] is False and i["state"] in analysis.STATES
    assert _items(v)["heads"]["name"] == "헤딩" and _items(v)["tables"]["name"] == "표"
    assert _items(v)["heads"]["llm"]["text"] == "LLM 판정 안 함"   # 결과가 아예 없으면 「스크립트 결과」 라고 하지 않는다
    assert _items(analysis.status(_sess({"stage2": _res(2)})))["heads"]["llm"]["text"] == "LLM 판정 안 함 — 스크립트 결과"


def test_first_run_turns_heads_then_tables():
    """첫 분석 = 2단계 → 3단계를 한 작업으로: 헤딩이 도는 동안 표는 대기, 헤딩이 끝나면 표가 돈다. 이미 있는 단계는 건너뛰므로 그 항목은 done 그대로."""
    a = _items(analysis.status(_sess({"job": _job(first=True)})))
    assert (a["heads"]["state"], a["tables"]["state"]) == ("running", "wait")
    v = analysis.status(_sess({"job": _job(first=True), "stage2": _res(2, templates=4, nodes=30)}))
    b = _items(v)
    assert (b["heads"]["state"], b["tables"]["state"]) == ("done", "running") and v["base"] == "running" and v["job"]["what"] == "첫 분석" and v["job"]["first"] is True
    assert b["heads"]["text"] == "헤딩 그래프 — 실행 2 · 템플릿 4 · 헤딩 30"
    c = _items(analysis.status(_sess({"job": _job(first=True), "stage3": _res(3, tables=7, cells=90)})))   # 표만 있던 문서 — 헤딩만 뽑는다
    assert (c["heads"]["state"], c["tables"]["state"]) == ("running", "done") and c["tables"]["text"] == "표 구조 — 실행 3 · 표 7 · 칸 90"
    done = analysis.status(_sess({"job": _job(first=True, status="done"), "stage2": _res(2), "stage3": _res(3)}))
    assert done["base"] == "done" and done["job"] is None and [i["state"] for i in _base2(done)] == ["done", "done"]


def test_llm_is_separate_and_follows_the_current_result():
    """LLM 판정은 기본 분석과 따로 — 결과가 있는 채 LLM 을 돌리면 헤딩은 done 그대로이고 LLM 만 도는 중. 지금 결과가 LLM 을 거쳤는지가 기준(스크립트로 다시 돌려 덮으면 none)."""
    both = {"stage2": _res(2), "stage3": _res(3)}
    a = _items(analysis.status(_sess({**both, "job": _job(stage=2, llm=True)})))
    assert a["heads"]["state"] == "done" and a["heads"]["llm"]["state"] == "running" and a["tables"]["state"] == "done" and a["tables"]["llm"]["state"] == "none"
    b = _items(analysis.status(_sess({"job": _job(stage=2, llm=True)})))   # 결과 없이 LLM 으로 — 기본도 도는 중
    assert b["heads"]["state"] == "running" and b["heads"]["llm"]["state"] == "running" and b["tables"]["state"] == "none"
    ok = _items(analysis.status(_sess({"stage2": _res(5, llm={"requested": True, "fallback": False, "applied": 80, "calls": 8, "failed": 0}), "stage3": _res(3)})))
    assert ok["heads"]["llm"] == {"state": "done", "text": "LLM 판정함 — 반영 80 · 호출 8", "error": None} and ok["tables"]["llm"]["state"] == "none"
    bad = _items(analysis.status(_sess({"stage2": _res(5, llm={"requested": True, "fallback": True, "error": "TimeoutError: x"}), "stage3": _res(3)})))
    assert bad["heads"]["state"] == "done" and bad["heads"]["llm"]["state"] == "failed" and bad["heads"]["llm"]["error"] == "TimeoutError: x"
    rerun = _items(analysis.status(_sess({**both, "job": _job(stage=3)})))   # 스크립트로 다시 — 그 항목만 도는 중
    assert (rerun["heads"]["state"], rerun["tables"]["state"], rerun["tables"]["llm"]["state"]) == ("done", "running", "none")
    stage1 = analysis.status(_sess({**both, "job": _job(stage=1)}))   # 1단계 작업(탭을 열 때 저절로)은 항목에 영향이 없다
    assert stage1["base"] == "done" and [i["state"] for i in _base2(stage1)] == ["done", "done"]
    assert stage1["busy"] is True and analysis.status(_sess({"job": _job(stage=1)}))["busy"] is True   # 그래도 도는 중이라 새 분석은 못 건다 — 화면이 「분석」 단추를 감춘다
    assert analysis.status(_sess(both))["busy"] is False and analysis.status(_sess({**both, "job": _job(stage=1, status="done")}))["busy"] is False
    # LLM 실행이 예외로 끝남 — 앞 결과(스크립트)는 그대로 done, LLM 만 failed. 지금 결과가 이미 LLM 을 거친 것이면 그 판정은 유효(done)
    boom = _items(analysis.status(_sess({**both, "job": _job(stage=2, llm=True, status="failed", error="RuntimeError: api")})))
    assert boom["heads"]["state"] == "done" and boom["heads"]["llm"] == {"state": "failed", "text": "LLM 판정 실행이 실패함 — 앞 결과는 그대로", "error": "RuntimeError: api"}
    assert boom["tables"]["llm"]["state"] == "none"
    kept = _items(analysis.status(_sess({"stage2": _res(5, llm={"requested": True, "fallback": False}), "stage3": _res(3), "job": _job(stage=2, llm=True, status="failed", error="E")})))
    assert kept["heads"]["llm"]["state"] == "done"
    script_fail = _items(analysis.status(_sess({**both, "job": _job(stage=2, status="failed", error="E")})))   # 스크립트 다시 돌리기가 실패 — LLM 과 무관
    assert script_fail["heads"]["llm"]["state"] == "none"


def test_failed_only_where_the_job_stopped_and_moved_is_not_a_state():
    f = analysis.status(_sess({"job": _job(first=True, status="failed", error="ValueError: boom")}))
    a = _items(f)
    assert (a["heads"]["state"], a["heads"]["error"], a["tables"]["state"], a["tables"]["error"]) == ("failed", "ValueError: boom", "none", None)
    assert f["base"] == "failed" and f["job"]["status"] == "failed" and f["job"]["error"] == "ValueError: boom"
    b = _items(analysis.status(_sess({"job": _job(first=True, status="failed", error="E"), "stage2": _res(2)})))
    assert (b["heads"]["state"], b["tables"]["state"]) == ("done", "failed")
    c = _items(analysis.status(_sess({"job": _job(stage=3, status="failed", error="E"), "stage2": _res(2), "stage3": _res(3)})))   # 결과가 있으면 실패한 다시 돌리기는 done 그대로
    assert c["tables"]["state"] == "done" and c["tables"]["error"] is None
    moved = analysis.status(_sess({"stage2": _res(2, rev=1), "stage3": _res(3, rev=3)}, rev=3))   # 문서를 고친 뒤 — 뼈대로 남는다(done) · moved 는 도움말용
    assert moved["base"] == "done" and [(i["state"], i["moved"]) for i in _base2(moved)] == [("done", True), ("done", False)]


def test_division_is_optional_and_only_when_it_applies():
    assert [i["key"] for i in analysis.status(_sess({}), division=False)["items"]] == FOUR
    none = _items(analysis.status(_sess({}), kind="rnd", division=True))["division"]
    assert none["optional"] is True and none["state"] == "none" and none["name"] == "구분 기준" and none["found"] == 0 and "옵션" in none["text"]
    run = _items(analysis.status(_sess({}, division={"reviewing": True}), division=True))["division"]
    assert run["state"] == "running"
    review = {"at": 9.0, "missing": {"missing": [{"id": "p1"}, {"id": "p2"}, {"id": "p3"}]}, "review": {"applied": [{"id": "h1"}]}}
    v = analysis.status(_sess({"stage2": _res(2), "stage3": _res(3)}, division={"review": review, "reviewing": False}), kind="rnd", division=True)
    d = _items(v)["division"]
    assert (d["state"], d["found"], d["applied"], d["at"]) == ("done", 3, 1, 9.0) and v["kind"] == "rnd"
    assert v["base"] == "done"   # 옵션 항목은 기본 분석 한마디에 안 든다(검토가 도는 중이어도)
    assert d["partial"] is False and d["error"] is None
    half = {"at": 9.0, "missing": None, "review": {"applied": []}, "errors": {"missing": "응답 없음"}}   # 빠진 자리 검토가 답이 없었다 — 결과는 남지만 다 본 것이 아니다
    h = _items(analysis.status(_sess({}, division={"review": half}), kind="rnd", division=True))["division"]
    assert (h["state"], h["found"], h["partial"], h["error"]) == ("done", 0, True, "빠진 자리 검토 — 응답 없음") and "답을 못 받은 검토" in h["text"]
    assert _items(analysis.status(_sess({}, division={"reviewing": True, "review": half}), division=True))["division"]["partial"] is False   # 다시 도는 중
    assert analysis.status(_sess({"stage2": _res(2), "stage3": _res(3)}, division={"reviewing": True}), division=True)["base"] == "done"
    docx = analysis.status(_sess({}, fmt="docx"), kind="general", division=True)   # 헤딩 추출은 hwpx 만 — 항목 없음
    assert docx == {"rev": 3, "format": "docx", "kind": "general", "base": "na", "busy": False, "job": None, "chain": None, "llmPlan": [], "items": []}


# ---------------------------------------------------------------- API(실제 문서)

def test_api_reads_only_and_follows_the_first_run(client):
    """갓 올린 문서(API 로만 — 화면이 아니라 첫 분석이 안 돈다): 읽기만 해서 none 그대로. 첫 분석을 걸면 done, 문서를 고쳐도 done(moved 만 참)."""
    d = _upload(client)
    v = client.get(f"/api/docs/{d}/analysis").json()
    assert v["format"] == "hwpx" and v["base"] == "none" and v["job"] is None and v["rev"] == 0
    assert [(i["key"], i["state"], i["llm"]["state"]) for i in _base2(v)] == [("heads", "none", "none"), ("tables", "none", "none")]
    assert client.get(f"/api/docs/{d}/headings").json()["job"] is None   # 상태를 읽어도 분석이 시작되지 않는다
    assert client.post(f"/api/docs/{d}/headings", json={"first": True}).status_code == 202
    _wait_heads(client, d)
    v = client.get(f"/api/docs/{d}/analysis").json()
    a = _items(v)
    assert v["base"] == "done" and v["job"] is None and (a["heads"]["state"], a["tables"]["state"]) == ("done", "done")
    assert (a["heads"]["run"], a["tables"]["run"]) == (2, 3) and a["heads"]["llm"]["state"] == a["tables"]["llm"]["state"] == "none" and not a["heads"]["moved"]
    assert a["heads"]["text"].startswith("헤딩 그래프 — 실행 2 · 템플릿 ") and a["tables"]["text"].startswith("표 구조 — 실행 3 · 표 ")
    doc = client.get(f"/api/docs/{d}").json()
    p = next(b for b in _paras(doc["blocks"]) if b["text"].strip())
    assert client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + " 고침"}).status_code == 200
    v2 = client.get(f"/api/docs/{d}/analysis").json()
    assert v2["rev"] > v["rev"] and v2["base"] == "done" and [(i["state"], i["moved"]) for i in _base2(v2)] == [("done", True), ("done", True)]


def test_api_shows_a_running_job_then_failed_without_result(client, monkeypatch):
    d = _upload(client)
    gate, entered = threading.Event(), threading.Event()

    def slow(sess, job, use_llm=False):
        entered.set()
        gate.wait(10)
        raise RuntimeError("멈춤")
    monkeypatch.setattr(heading_runs, "run_first", slow)
    assert client.post(f"/api/docs/{d}/headings", json={"first": True}).status_code == 202
    assert entered.wait(10)
    v = client.get(f"/api/docs/{d}/analysis").json()
    a = _items(v)
    assert v["base"] == "running" and v["busy"] is True and v["job"]["status"] == "running" and v["job"]["first"] is True and (a["heads"]["state"], a["tables"]["state"]) == ("running", "wait")
    gate.set()
    _wait_heads(client, d)
    v = client.get(f"/api/docs/{d}/analysis").json()
    a = _items(v)
    assert v["base"] == "failed" and v["busy"] is False and a["heads"]["state"] == "failed" and "멈춤" in a["heads"]["error"] and a["tables"]["state"] == "none" and v["job"]["status"] == "failed"


def test_api_division_item_kind_and_docx(client):
    """구분 기준 항목 = hwpx 이고 지원 양식일 때만(문서의 성질) · kind = 작업에 적힌 작업 종류(화면이 그것으로 보일지 정한다) · docx 는 항목 없음. 404 = 없는 문서."""
    small = client.get(f"/api/docs/{_upload(client)}/analysis").json()
    assert [i["key"] for i in small["items"]] == FOUR   # 기술수요조사서 — 구분 기준 지원 양식이 아니다
    f = _upload(client, FORM)
    v = client.get(f"/api/docs/{f}/analysis").json()
    assert [i["key"] for i in v["items"]] == FOUR + ["division"] and _items(v)["division"]["state"] == "none" and _items(v)["division"]["optional"] is True
    assert client.get(f"/api/docs/{f}").status_code == 200 and client.get(f"/api/docs/{f}/analysis").json()["kind"] == "rnd"   # 문서를 열면 양식에서 짐작한 작업 종류가 작업에 적힌다
    server.DOCS[f].division["reviewing"] = True
    assert _items(client.get(f"/api/docs/{f}/analysis").json())["division"]["state"] == "running"
    server.DOCS[f].division["reviewing"] = False
    server.DOCS[f].division["review"] = {"at": 1.0, "missing": {"missing": [{"id": "a"}]}, "review": None}
    dv = _items(client.get(f"/api/docs/{f}/analysis").json())["division"]
    assert (dv["state"], dv["found"], dv["applied"]) == ("done", 1, 0)
    x = _upload(client, DOCX)
    assert client.get(f"/api/docs/{x}/analysis").json() | {"kind": ""} == {"rev": 0, "format": "docx", "kind": "", "base": "na", "busy": False, "job": None, "chain": None, "llmPlan": [], "items": []}
    assert client.get("/api/docs/nope/analysis").status_code == 404


# ---------------------------------------------------------------- 넷 · 진행표 · LLM 검증·보완(2026-11-16 — ② §20)

def _ov(templates, lines):
    return {"run": [2, 102.0], "templates": templates, "lines": lines}


def _var(counts, rep=True):
    return {"total": sum(counts), "rep": "p1" if rep else None, "repMissing": not rep, "others": sum(counts[1:]) if rep else 0, "groups": [{"count": n} for n in counts]}


OV = _ov({"1": {"no": "1", "chain": ["□", "o", "-"]}, "2": {"no": "2", "chain": ["-"]}, "9": {"no": "9", "chain": ["*"]}},
         {"p1": {"tpl": "1"}, "p2": {"tpl": "1"}, "p3": {"tpl": "2"}})   # T9 는 줄이 없다 — 세지 않는다
VARS = {"1": {"1": _var([5, 2]), "2": _var([4])}, "2": {"1": _var([3])}}


def test_templates_and_formats_count_from_overlay_variants_and_plans():
    st = {"stage2": _res(2), "stage3": _res(3, calc={"formulas": 12, "ok": 12, "mismatch": 0})}
    v = analysis.status(_sess(st), outline=(OV, VARS), plans={})
    a = _items(v)
    assert [i["key"] for i in v["items"]] == FOUR and v["base"] == "done"
    t = a["templates"]
    assert (t["state"], t["count"], t["text"], t["llm"]["state"]) == ("done", 2, "T1 □ › o › - · T2 -", "none")
    f = a["formats"]
    assert (f["state"], f["levels"], f["aligned"], f["groups"], f["others"]) == ("done", 3, 2, 4, 2)
    assert f["apply"] == {"state": "none", "text": "맞춘 레벨 2/3 · 대표와 다른 줄 2"} and f["text"] == "레벨 3 · 서식 4가지"
    assert f["llm"]["state"] == "none" and f["llm"]["need"] == 1 and f["llm"]["list"] == [{"tpl": "1", "no": "1", "state": "none"}]
    assert a["tables"]["calc"] == {"formulas": 12, "ok": 12, "mismatch": 0} and a["heads"]["rules"] is None
    assert [(x["key"], x["run"]) for x in v["llmPlan"]] == [("heads", True), ("tables", True), ("formats", True)] and v["chain"] is None
    # 계획: 같은 문서 차례 = 받음(done) · 옛 차례 = stale(다시 받을 것) · 적용함 = applied(done)
    got = _items(analysis.status(_sess(st), outline=(OV, VARS), plans={"1": {"rev": 3}}))["formats"]["llm"]
    assert (got["state"], got["planned"], got["text"]) == ("done", 1, "서식 정리 계획 1/1 템플릿 — 받음 1")
    old = _items(analysis.status(_sess(st), outline=(OV, VARS), plans={"1": {"rev": 1}}))["formats"]["llm"]
    assert (old["state"], old["stale"], old["list"][0]["state"]) == ("none", 1, "stale") and "옛 계획 1" in old["text"]
    rec = {"tpl": "1", "rev": 1, "at": 7.0, "applied": {"at": 8.0}}   # 반영함 = 기록의 applied + 오버레이의 표(agent[템플릿] = 그 계획의 at — tpl_agent_api.applied 가 적는다)
    done = _items(analysis.status(_sess(st), outline=({**OV, "agent": {"1": 7.0}}, VARS), plans={"1": rec}))["formats"]["llm"]
    assert (done["state"], done["applied"], done["done"], done["list"][0]["state"]) == ("done", 1, 1, "applied")
    # 반영했다가 되돌림(실행 취소 · 모두 되돌리기 — 오버레이가 되돌아가 표가 없다) · 다른 계획의 표 = 반영함이 아니다 → 옛 계획(다시 받을 것)
    for ov in (OV, {**OV, "agent": {}}, {**OV, "agent": {"1": 6.0}}, {**OV, "agent": {"2": 7.0}}):
        undone = _items(analysis.status(_sess(st), outline=(ov, VARS), plans={"1": rec}))["formats"]["llm"]
        assert (undone["state"], undone["applied"], undone["stale"], undone["done"], undone["list"][0]["state"]) == ("none", 0, 1, 0, "stale"), ov.get("agent")
    assert analysis.plan_state({**rec, "rev": 3}, 3, OV) == "stale"   # 문서 차례가 같아도 반영했던 계획은 그대로 다시 반영하지 않는다
    assert analysis.plan_state(rec, 1) == "stale" and analysis.plan_state(None, 1, OV) == "none" and analysis.plan_state({"rev": 1}, 1) == "planned"
    # 갈래가 모두 하나 — 정리할 것 없음(LLM 칸 done) · 반영 done
    one = _items(analysis.status(_sess(st), outline=(OV, {"1": {"1": _var([5])}}), plans={}))["formats"]
    assert one["llm"]["state"] == "done" and one["llm"]["text"].startswith("정리할 것 없음") and one["apply"]["state"] == "done"
    # 대표가 없는 레벨 — 가장 많은 갈래를 대표로 보고 다른 줄을 센다 · 정리할 템플릿
    nr = _items(analysis.status(_sess(st), outline=(OV, {"1": {"1": _var([2, 6], rep=False)}}), plans={}))["formats"]
    assert nr["others"] == 2 and nr["llm"]["need"] == 1
    # LLM 을 다 거친 문서 — 누르면 돌 것이 없다
    llm_ok = {"requested": True, "fallback": False}
    full = analysis.status(_sess({"stage2": _res(2, llm=llm_ok), "stage3": _res(3, llm=llm_ok)}), outline=(OV, VARS), plans={"1": {"rev": 3}})
    assert [x["run"] for x in full["llmPlan"]] == [False, False, False] and _items(full)["templates"]["llm"]["state"] == "done"
    # 헤딩 그래프가 없으면 템플릿 · 서식도 없음
    none = _items(analysis.status(_sess({})))
    assert (none["templates"]["state"], none["formats"]["state"], none["formats"]["levels"]) == ("none", "none", 0)


def test_chain_turns_follow_each_part():
    """단계마다 제 상태로 — 헤딩(+템플릿) 먼저, 그 뒤 표 · 서식은 같이(둘 다 「도는 중」 일 수 있다 — 2026-11-16 사용자 "병렬로 할 수 있으면 병렬로")."""
    both = {"stage2": _res(2), "stage3": _res(3)}

    def chain(heads, tables, formats, status="running", error=None, fmsg=""):
        j = _job(stage=2 if heads == "running" else 3, llm=True, status=status, error=error)
        j.chain, j.parts = "llm", [{"key": "heads", "name": "h", "no": 1, "status": heads, "msg": ""}, {"key": "tables", "name": "t", "no": 2, "status": tables, "msg": ""},
                                   {"key": "formats", "name": "f", "no": 2, "status": formats, "msg": fmsg}]
        return j
    v = analysis.status(_sess({**both, "job": chain("running", "wait", "wait")}), outline=(OV, VARS), plans={})
    a = _items(v)
    assert (a["heads"]["state"], a["heads"]["llm"]["state"], a["templates"]["llm"]["state"]) == ("done", "running", "running")
    assert (a["tables"]["state"], a["tables"]["llm"]["state"], a["formats"]["llm"]["state"]) == ("done", "wait", "wait")
    assert v["base"] == "done" and v["busy"] is True and v["job"]["what"] == "LLM 검증·보완" and v["job"]["chain"] == "llm" and v["chain"]["steps"][0]["key"] == "heads"
    assert (v["chain"]["running"], v["chain"]["at"], [s["no"] for s in v["chain"]["steps"]]) == (["heads"], "heads", [1, 2, 2])
    # 표 · 서식 같이 — 둘 다 도는 중
    v2 = analysis.status(_sess({**both, "job": chain("ok", "running", "running", fmsg="T1 · T2 계획 받는 중(같이 2) — 끝남 0/2")}), outline=(OV, VARS), plans={})
    b = _items(v2)
    assert (b["heads"]["llm"]["state"], b["tables"]["llm"]["state"], b["formats"]["llm"]["state"]) == ("none", "running", "running")
    assert v2["chain"]["running"] == ["tables", "formats"] and "같이 2" in b["formats"]["llm"]["text"]
    # 서식이 먼저 끝나도 표가 도는 동안 서식 칸은 받은 계획을 센다(「대기」 가 아니다)
    e = _items(analysis.status(_sess({**both, "job": chain("ok", "running", "ok")}), outline=(OV, VARS), plans={"1": {"rev": 3}}))
    assert (e["tables"]["llm"]["state"], e["formats"]["llm"]["state"]) == ("running", "done")
    # 막 시작해 단계가 아직 안 적힘 — 헤딩부터
    j0 = _job(stage=2, llm=True)
    j0.chain = "llm"
    z = _items(analysis.status(_sess({**both, "job": j0}), outline=(OV, VARS), plans={}))
    assert (z["heads"]["llm"]["state"], z["tables"]["llm"]["state"], z["formats"]["llm"]["state"]) == ("running", "wait", "wait")
    # 실패 — 실패한 단계에만
    c = _items(analysis.status(_sess({**both, "job": chain("ok", "failed", "ok", "failed", "Stop: 표")}), outline=(OV, VARS), plans={}))
    assert (c["tables"]["llm"]["state"], c["tables"]["llm"]["error"], c["heads"]["llm"]["state"]) == ("failed", "Stop: 표", "none")
    d = _items(analysis.status(_sess({**both, "job": chain("ok", "ok", "failed", "failed", "Stop: 서식", fmsg="실패 T1: 502")}), outline=(OV, VARS), plans={}))
    assert (d["formats"]["llm"]["state"], d["formats"]["llm"]["error"], d["tables"]["llm"]["state"]) == ("failed", "실패 T1: 502", "none")
    # 돌 것 — 차례 번호(같은 번호 = 같이) · 같이 도는 것이 있을 때만 「같이」 라고 적는다
    plan = v["llmPlan"]
    assert [(x["key"], x["no"], x["run"]) for x in plan] == [("heads", 1, True), ("tables", 2, True), ("formats", 2, True)]
    assert "서식과 같이" in plan[1]["why"] and "표와 같이" in plan[2]["why"]
    llm_ok = {"requested": True, "fallback": False}
    only_t = analysis.status(_sess({"stage2": _res(2, llm=llm_ok), "stage3": _res(3)}), outline=(OV, VARS), plans={"1": {"rev": 3}})["llmPlan"]
    assert [x["run"] for x in only_t] == [False, True, False] and "같이" not in only_t[1]["why"]


def _llm_ok(stage, applied=3):
    def fake(sess, job, use_llm):
        assert use_llm is True
        res = heading_runs.state(sess)[f"stage{stage}"]
        res["llm"] = {**(res.get("llm") or {}), "requested": True, "fallback": False, "applied": applied, "calls": 1}
        fake.calls += 1
        return 40 + stage
    fake.calls = 0
    return fake


def _wait_job(c, d, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        j = c.get(f"/api/docs/{d}/headings").json()["job"]
        if j and j["status"] != "running":
            return j
        time.sleep(0.05)
    raise AssertionError("LLM 검증·보완이 끝나지 않음")


def test_api_llm_chain_in_order_skips_what_is_done_and_keeps_plans(client, monkeypatch):
    """헤딩(+템플릿) → 표 → 서식(계획만) 차례 · 문서는 안 바뀜 · 다시 누르면 다 건너뜀 · 받은 계획은 작업 폴더에 남는다."""
    from app import llm, tpl_agent_api, works
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    d = _upload(client, FORM)
    assert client.post(f"/api/docs/{d}/headings", json={"first": True}).status_code == 202
    _wait_heads(client, d)
    v0 = client.get(f"/api/docs/{d}/analysis").json()
    need = _items(v0)["formats"]["llm"]["need"]
    assert need >= 1 and [x["run"] for x in v0["llmPlan"]] == [True, True, True]
    f2, f3 = _llm_ok(2), _llm_ok(3)
    monkeypatch.setattr(heading_runs, "run_stage2", f2)
    monkeypatch.setattr(heading_runs, "run_stage3", f3)
    asked = []

    def fake_call(schema, content, what, **kw):
        asked.append(what)
        return {"data": {"summary": "정리", "levels": []}, "backend": "api", "ms": 1, "costUsd": 0.0, "error": None, "model": kw.get("model"), "effort": kw.get("effort")}
    monkeypatch.setattr(llm, "call", fake_call)
    rev = server.DOCS[d].rev
    r = client.post(f"/api/docs/{d}/analysis/llm", json={})
    assert r.status_code == 202, r.text
    assert r.json()["chain"] == "llm"
    j = _wait_job(client, d)
    assert j["status"] == "done", j
    assert (f2.calls, f3.calls, len(asked)) == (1, 1, need) and set(asked) == {"tpl-agent"} and server.DOCS[d].rev == rev   # 문서는 안 바뀐다
    v = client.get(f"/api/docs/{d}/analysis").json()
    a = _items(v)
    assert (a["heads"]["llm"]["state"], a["templates"]["llm"]["state"], a["formats"]["llm"]["state"], a["tables"]["llm"]["state"]) == ("done",) * 4
    assert [s["status"] for s in v["chain"]["steps"]] == ["ok", "ok", "ok"] and [x["run"] for x in v["llmPlan"]] == [False, False, False]
    plans = client.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]
    assert len(plans) == need and {p["state"] for p in plans.values()} == {"planned"}
    assert (works.folder(d) / "outline_agent" / "plans.json").is_file()
    del server.DOCS[d].tpl_plans   # 서버를 다시 켠 것처럼 — 작업 폴더에서 다시 읽는다
    assert set(client.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]) == set(plans)
    # 다시 누름 — 다 건너뜀(유료 호출 없음)
    assert client.post(f"/api/docs/{d}/analysis/llm", json={}).status_code == 202
    _wait_job(client, d)
    assert (f2.calls, f3.calls, len(asked)) == (1, 1, need)
    assert [s["status"] for s in client.get(f"/api/docs/{d}/analysis").json()["chain"]["steps"]] == ["skip", "skip", "skip"]
    assert client.post(f"/api/docs/{d}/analysis/llm", json={"skill": "nope"}).status_code == 404
    assert client.delete(f"/api/docs/{d}/analysis/llm").status_code == 409   # 도는 것이 없음
    x = _upload(client, DOCX)
    assert client.post(f"/api/docs/{x}/analysis/llm", json={}).status_code == 400
    assert tpl_agent_api.plans(server.DOCS[d], [0, 0]) == {}   # 다른 헤딩 그래프의 계획은 없는 것


def test_api_llm_chain_stops_on_fallback_and_on_request(client, monkeypatch):
    d = _upload(client, FORM)
    assert client.post(f"/api/docs/{d}/headings", json={"first": True}).status_code == 202
    _wait_heads(client, d)

    def fallback(sess, job, use_llm):
        st = heading_runs.state(sess)
        st["stage2"]["llm"] = {**st["stage2"]["llm"], "requested": True, "fallback": True, "error": "TimeoutError: api"}
        return 9
    monkeypatch.setattr(heading_runs, "run_stage2", fallback)
    assert client.post(f"/api/docs/{d}/analysis/llm", json={}).status_code == 202
    j = _wait_job(client, d)
    assert j["status"] == "failed" and "헤딩 그래프 LLM 판정을 못 함" in j["error"]
    v = client.get(f"/api/docs/{d}/analysis").json()
    assert [s["status"] for s in v["chain"]["steps"]] == ["failed", "wait", "wait"] and v["job"]["what"] == "LLM 검증·보완"
    assert _items(v)["heads"]["llm"]["state"] == "failed" and _items(v)["tables"]["llm"]["state"] == "none"
    # 멈추기 — 지금 일이 끝나면 멈춘다(뒤 일은 「멈춤」)
    gate, entered = threading.Event(), threading.Event()
    ok2 = _llm_ok(2)

    def slow(sess, job, use_llm):
        entered.set()
        gate.wait(10)
        return ok2(sess, job, use_llm)
    monkeypatch.setattr(heading_runs, "run_stage2", slow)
    monkeypatch.setattr(heading_runs, "run_stage3", _llm_ok(3))
    assert client.post(f"/api/docs/{d}/analysis/llm", json={}).status_code == 202
    assert entered.wait(10)
    assert client.post(f"/api/docs/{d}/analysis/llm", json={}).status_code == 409   # 헤딩 작업 자리 하나
    assert client.post(f"/api/docs/{d}/headings", json={"stage": 3}).status_code == 409
    assert client.delete(f"/api/docs/{d}/analysis/llm").json() == {"stopping": True}
    gate.set()
    j = _wait_job(client, d)
    v = client.get(f"/api/docs/{d}/analysis").json()
    assert j["status"] == "done" and [s["status"] for s in v["chain"]["steps"]] == ["ok", "stopped", "stopped"] and v["chain"]["stopping"] is True


def _chain_job(sess):
    j = heading_runs.Job(2, True, sess.rev)
    j.chain = "llm"
    return j


def _fake_sess(stage2_llm=False, stage3_llm=False):
    llm_ok = {"requested": True, "fallback": False}
    st = {"stage2": _res(2, llm=llm_ok if stage2_llm else None), "stage3": _res(3, llm=llm_ok if stage3_llm else None)}
    return _sess(st)


TPLS = {"1": {"1": _var([5, 2])}, "2": {"1": _var([3, 1])}, "3": {"1": _var([4, 4])}}
OV3 = _ov({"1": {"no": "1"}, "2": {"no": "2"}, "3": {"no": "3"}}, {})


def test_chain_runs_tables_and_formats_together_and_templates_together(monkeypatch):
    """① 헤딩 · 템플릿 먼저 혼자 → ② 표 · ③ 서식이 같이 · ③ 의 템플릿끼리도 같이(PLAN_WORKERS 까지) — 실제로 겹쳐 도는지 본다(둘이 서로를 기다리면 시간 초과)."""
    from app import analysis_llm
    sess = _fake_sess()
    job = _chain_job(sess)
    order, lock = [], threading.Lock()
    heads_done = threading.Event()
    t_in, f_in = threading.Event(), threading.Event()
    p_in = threading.Barrier(3, timeout=10)   # 템플릿 셋이 한꺼번에 들어와야 지나간다

    def s2(s, j, use_llm):
        with lock:
            order.append("heads")
        s.heads["stage2"]["llm"] = {"requested": True, "fallback": False}
        heads_done.set()
        return 42

    def s3(s, j, use_llm):
        assert heads_done.is_set()   # ① 뒤
        t_in.set()
        assert f_in.wait(10), "표가 도는 동안 서식이 시작하지 않음"   # 서식과 겹친다
        s.heads["stage3"]["llm"] = {"requested": True, "fallback": False}
        with lock:
            order.append("tables")
        return 43
    monkeypatch.setattr(heading_runs, "run_stage2", s2)
    monkeypatch.setattr(heading_runs, "run_stage3", s3)
    monkeypatch.setattr(analysis_llm.works, "log", lambda *a, **k: None)

    def plan(s, tid):
        assert heads_done.is_set()
        f_in.set()
        p_in.wait()   # 셋이 같이 들어와야 풀린다
        assert t_in.wait(10)
        with lock:
            order.append(f"T{tid}")
    n = analysis_llm.run(sess, job, outline=lambda s: (OV3, TPLS), plans=lambda s, g: {}, plan=plan)
    assert n == 43 and order[0] == "heads" and set(order[1:]) == {"tables", "T1", "T2", "T3"}
    steps = {p["key"]: p for p in job.parts}
    assert [(p["key"], p["no"], p["status"]) for p in job.parts] == [("heads", 1, "ok"), ("tables", 2, "ok"), ("formats", 2, "ok")]
    assert steps["formats"]["msg"].startswith("계획 받음 T1 · T2 · T3")   # 끝난 차례가 아니라 템플릿 차례


def test_chain_parallel_failure_keeps_the_other_and_stop_skips_unstarted_templates(monkeypatch):
    from app import analysis_llm
    monkeypatch.setattr(analysis_llm.works, "log", lambda *a, **k: None)
    # 표가 실패해도 같이 돈 서식은 제 일을 마친다 — 작업은 표의 까닭으로 실패
    sess = _fake_sess(stage2_llm=True)
    job = _chain_job(sess)

    def s3_fail(s, j, use_llm):
        s.heads["stage3"]["llm"] = {"requested": True, "fallback": True, "error": "TimeoutError"}
        return 7
    monkeypatch.setattr(heading_runs, "run_stage3", s3_fail)
    got = []
    with pytest.raises(analysis_llm.Stop, match="표 구조 LLM 판정을 못 함"):
        analysis_llm.run(sess, job, outline=lambda s: (OV3, TPLS), plans=lambda s, g: {}, plan=lambda s, tid: got.append(tid))
    assert sorted(got) == ["1", "2", "3"] and [p["status"] for p in job.parts] == ["skip", "failed", "ok"]
    # 멈추기 — 도는 템플릿은 끝내고, 아직 시작하지 않은 템플릿은 하지 않는다
    monkeypatch.setattr(analysis_llm, "PLAN_WORKERS", 1)
    sess = _fake_sess(stage2_llm=True, stage3_llm=True)
    job = _chain_job(sess)
    done = []

    def plan_stop(s, tid):
        job.stop = True   # 첫 템플릿을 받는 동안 멈추기를 누름
        done.append(tid)
    analysis_llm.run(sess, job, outline=lambda s: (OV3, TPLS), plans=lambda s, g: {}, plan=plan_stop)
    f = {p["key"]: p for p in job.parts}["formats"]
    assert done == ["1"] and f["status"] == "partial" and "멈춤 — 남은 템플릿 2" in f["msg"]


# ---------------------------------------------------------------- 헤딩 그래프(LLM) → 서식 정리 계획 · 서식 계획만 · 반영하면 바뀔 줄 수(2026-11-16 — 사용자 답 「헤딩 LLM 판정에 늘 이어서」 · 「확인 뒤 한 번에 반영」)

def test_formats_item_counts_what_applying_the_plans_would_change():
    """받아 둔 계획(지금 문서 차례)마다 에이전트가 고른 그대로 반영하면 바뀔 줄 · 다른 템플릿으로 옮길 줄 — 헤딩 추출 탭 진행 줄 「조정」 의 「모두 반영」 이 보이는 수."""
    st = {"stage2": _res(2), "stage3": _res(3)}

    def g(gid, n):
        return {"group": gid, "para": f"p{gid}", "count": n}
    plan = {"levels": [{"level": 1, "rep": g("g1", 5), "match": [g("g2", 2)], "keep": [g("g5", 1)], "split": [{"sfx": "a", "rep": g("g3", 4), "match": [g("g4", 1)]}]},
                       {"level": 2, "rep": g("g1", 4), "match": [], "keep": [], "split": []}]}
    f = _items(analysis.status(_sess(st), outline=(OV, VARS), plans={"1": {"rev": 3, "plan": plan}}))["formats"]["llm"]
    assert (f["planned"], f["change"], f["moved"]) == (1, 3, 5)
    assert f["list"] == [{"tpl": "1", "no": "1", "state": "planned", "change": 3, "moved": 5, "reps": 0, "at": None, "kept": 0, "unanswered": 0, "omitted": 0}]   # at = 계획의 표시 · reps = 대표를 바꿀 레벨 · 남는 것(그대로 둔 줄 · 답 없던 줄 · 못 본 갈래)
    old = _items(analysis.status(_sess(st), outline=(OV, VARS), plans={"1": {"rev": 1, "plan": plan}}))["formats"]["llm"]   # 옛 계획 — 반영할 수 없으므로 세지 않는다
    assert (old["stale"], old["change"], old["moved"]) == (1, 0, 0) and "change" not in old["list"][0] and (f["done"], old["done"]) == (0, 0)
    # 반영한 계획 수(done)는 모든 템플릿에서 센다 — 다 맞춰 「정리할 템플릿」 에서 빠진 것도(진행 줄 「조정」 의 ✓)
    even = {"1": {"1": _var([7]), "2": _var([4])}, "2": {"1": _var([3])}}
    rec = {"tpl": "1", "rev": 3, "at": 2.0, "plan": plan, "applied": {"at": 1.0, "rev": 4, "changed": 3}}
    after = _items(analysis.status(_sess(st), outline=({**OV, "agent": {"1": 2.0}}, even), plans={"1": rec}))["formats"]["llm"]
    assert (after["need"], after["applied"], after["done"], after["state"]) == (0, 0, 1, "done")
    back = _items(analysis.status(_sess(st), outline=(OV, even), plans={"1": rec}))["formats"]["llm"]   # 반영을 되돌린 계획(오버레이에 표가 없다)은 안 센다
    assert (back["need"], back["done"]) == (0, 0)
    none = _items(analysis.status(_sess(st), outline=(OV, VARS), plans={}))["formats"]["llm"]
    assert (none["change"], none["moved"]) == (0, 0)


def test_formats_item_counts_rep_changes_and_what_an_applied_plan_left():
    """조정 길의 빈 곳(2026-11-16 astra): ① 대표만 바꾸는 레벨도 반영할 것으로 센다(reps — 「맞출 줄 0 · 대표 변경 1」 도 「전체 실행」 이 조정을 돌린다)
    ② 반영한 계획이 남긴 줄(에이전트가 그대로 둔 줄 · 답이 없어 안 바꾼 줄)은 반영한 뒤에도 센다(left — 지금 갈래로 다시 세어, 그 뒤 사람이 맞춘 갈래는 빠진다)."""
    from app import tpl_agent
    st = {"stage2": _res(2), "stage3": _res(3)}
    raw_k, raw_u = {"lead": "  "}, {"lead": "   "}   # 남긴 갈래의 비교 값(갈래 지문 = 레벨 + 비교 값)

    def g(gid, n, **kw):
        return {"group": gid, "para": f"p{gid}", "count": n, **kw}
    plan = {"levels": [{"level": 1, "rep": g("g1", 5), "match": [g("g2", 2)], "split": [],
                        "keep": [g("g3", 1, auto=False, sig=tpl_agent.group_sig(1, raw_k)), g("g4", 2, auto=True, sig=tpl_agent.group_sig(1, raw_u))]},
                       {"level": 2, "rep": g("g2", 4, changed=True), "match": [], "split": [], "keep": [g("g1", 3, auto=False, sig="옛 대표 갈래")]}],
            "left": {"kept": 4, "unanswered": 2}, "omitted": 0}
    f = _items(analysis.status(_sess(st), outline=(OV, VARS), plans={"1": {"rev": 3, "plan": plan}}))["formats"]["llm"]
    row = f["list"][0]
    assert (row["state"], row["change"], row["moved"], row["reps"], row["kept"], row["unanswered"]) == ("planned", 2, 0, 1, 4, 2) and "left" not in row
    assert f["reps"] == 1 and f["left"] == {"kept": 0, "unanswered": 0}                      # left = **반영한** 계획이 남긴 것 — 받아 둔 계획의 kept·unanswered 와 따로
    only = {"levels": [{"level": 2, "rep": g("g2", 4, changed=True), "match": [], "split": [], "keep": []}]}   # 대표만 바꾸는 계획 — 바뀔 줄은 0 이어도 반영할 것이 있다
    f1 = _items(analysis.status(_sess(st), outline=(OV, VARS), plans={"1": {"rev": 3, "plan": only}}))["formats"]["llm"]
    assert (f1["planned"], f1["change"], f1["moved"], f1["reps"]) == (1, 0, 0, 1)

    def grp(n, raw, rep=False):
        return {"count": n, "rep": rep, "raw": raw, "key": "px"}
    now = {"1": {"1": {"total": 10, "rep": "p1", "repMissing": False, "others": 3, "groups": [grp(7, {"lead": " "}, True), grp(1, raw_k), grp(2, raw_u)]}, "2": _var([7])}, "2": {"1": _var([3])}}
    rec = {"tpl": "1", "rev": 3, "at": 2.0, "plan": plan, "applied": {"at": 1.0, "rev": 4, "changed": 2}}
    done = _items(analysis.status(_sess(st), outline=({**OV, "agent": {"1": 2.0}}, now), plans={"1": rec}))["formats"]["llm"]
    row = done["list"][0]
    assert row["state"] == "applied" and row["left"] == {"kept": 1, "unanswered": 2} and "kept" not in row and "change" not in row
    assert done["left"] == {"kept": 1, "unanswered": 2} and (done["kept"], done["unanswered"], done["reps"]) == (0, 0, 0)
    fixed = {**now, "1": {**now["1"], "1": {"total": 10, "rep": "p1", "repMissing": False, "others": 1, "groups": [grp(9, {"lead": " "}, True), grp(1, raw_k)]}}}   # 답 없던 갈래를 사람이 대표에 맞췄다
    assert _items(analysis.status(_sess(st), outline=({**OV, "agent": {"1": 2.0}}, fixed), plans={"1": rec}))["formats"]["llm"]["left"] == {"kept": 1, "unanswered": 0}
    undone = _items(analysis.status(_sess(st), outline=(OV, now), plans={"1": rec}))["formats"]["llm"]   # 반영을 되돌린 계획(오버레이에 표가 없다) — 남긴 것으로 세지 않는다
    assert undone["left"] == {"kept": 0, "unanswered": 0} and "left" not in undone["list"][0]


def test_plan_left_does_not_drop_a_variant_just_because_its_key_line_is_gone():
    """반영한 계획이 남긴 줄(plan_left) — 2026-11-17 astra 2차 검토 2번: 대표를 못 고른 레벨의 답 없는 갈래 G1 = {a, b}(열쇠 줄 a) · G2 = {c}. 그 뒤 사람이 c 를 대표로 정하고 **a 만** 맞추면
    b 는 답 없던 서식 그대로다(열쇠 줄은 이제 b) — 옛 열쇠 줄 a 를 못 찾는다고 0 이 되면 안 된다. 지문(sig)이 있으면 서식으로 찾고, 지문이 없는 옛 계획은 **지금 갈래로 증명될 때만** 해결된 것으로 본다."""
    from app import tpl_agent

    def k(gid, para, n, **kw):
        return {"group": gid, "para": para, "count": n, **kw}

    def grp(key, paras, rep=False, raw=None):
        return {"key": key, "paras": list(paras), "count": len(paras), "rep": rep, "raw": raw or {"lead": key}}

    def lv(*groups):
        return {"1": {"groups": list(groups)}}
    old = {"levels": [{"level": 1, "rep": None, "match": [], "split": [], "keep": [k("g1", "a", 2, auto=True), k("g2", "c", 1, auto=True)]}]}   # 지문 없는 옛 계획
    assert analysis.plan_left(old, lv(grp("a", "ab"), grp("c", "c"))) == {"kept": 0, "unanswered": 3}             # 반영 직후 — 그대로
    after = lv(grp("c", "ca", rep=True), grp("b", "b"))                                                          # c 를 대표로 · a 만 맞춤 — b 는 그대로
    assert analysis.plan_left(old, after) == {"kept": 0, "unanswered": 1}                                         # 열쇠 줄이 떠났다고 사라지지 않는다
    assert analysis.plan_left(old, lv(grp("c", "cab", rep=True))) == {"kept": 0, "unanswered": 0}                 # b 까지 맞춤 — 대표와 다른 줄이 없으니 남은 것도 없다(증명됨)
    assert analysis.plan_left(old, lv(grp("c", "c", rep=True), grp("b", "ab"))) == {"kept": 0, "unanswered": 2}    # 열쇠 줄이 그 갈래의 줄로 남아 있으면(열쇠만 바뀜) 그 갈래의 지금 줄 수
    sig_a, sig_c = tpl_agent.group_sig(1, {"lead": "A"}), tpl_agent.group_sig(1, {"lead": "C"})
    new = {"levels": [{"level": 1, "rep": None, "match": [], "split": [], "keep": [k("g1", "a", 2, auto=True, sig=sig_a), k("g2", "c", 1, auto=True, sig=sig_c)]}]}   # 지문이 있는 계획 — 서식으로 찾는다
    assert analysis.plan_left(new, lv(grp("c", "ca", rep=True, raw={"lead": "C"}), grp("b", "b", raw={"lead": "A"}))) == {"kept": 0, "unanswered": 1}
    assert analysis.plan_left(new, lv(grp("c", "ca", rep=True, raw={"lead": "C"}), grp("b", "b", raw={"lead": "Z"}))) == {"kept": 0, "unanswered": 0}   # 그 서식의 줄이 없다 — 남은 줄은 그 뒤 생긴 다른 서식(이 계획이 남긴 것이 아니다)
    # 지문 없는 옛 계획에서 못 찾은 갈래는 답 없는 쪽부터 센다(검토 안 된 줄을 놓치지 않게) — 지금 남은 대표와 다른 줄 수를 넘지 않는다
    mixed = {"levels": [{"level": 1, "rep": k("g0", "r", 4), "match": [], "split": [], "keep": [k("g1", "a", 2, auto=False), k("g2", "x", 3, auto=True)]}]}
    assert analysis.plan_left(mixed, lv(grp("r", "r", rep=True), grp("b", "b"))) == {"kept": 0, "unanswered": 1}
    assert analysis.plan_left(mixed, lv(grp("r", "r", rep=True), grp("b", "bcde"))) == {"kept": 1, "unanswered": 3}


def test_level_without_a_rep_is_not_an_aligned_level():
    """대표가 없는 레벨은 갈래가 하나뿐이어도 「맞춘 레벨」 이 아니다 — 대표가 없으면 자리 맞춤도 새 줄의 서식도 정해지지 않는다(2026-11-16 astra: groups <= 1 만 보고 세었다)."""
    st = {"stage2": _res(2), "stage3": _res(3)}
    f = _items(analysis.status(_sess(st), outline=(OV, {"1": {"1": _var([5], rep=False), "2": _var([4])}}), plans={}))["formats"]
    assert (f["levels"], f["aligned"], f["noRep"]) == (2, 1, 1) and f["apply"] == {"state": "none", "text": "맞춘 레벨 1/2 · 대표 없는 레벨 1"}
    ok = _items(analysis.status(_sess(st), outline=(OV, {"1": {"1": _var([5]), "2": _var([4])}}), plans={}))["formats"]
    assert (ok["levels"], ok["aligned"], ok["noRep"]) == (2, 2, 0) and ok["apply"] == {"state": "done", "text": "맞춘 레벨 2/2"}


def test_chain_name_and_parts_follow_the_chain():
    """이어 돌리기 셋 — llm(LLM 검증·보완) · heads(헤딩 그래프(LLM) → 서식 계획: 표는 없다) · formats(서식 계획만). 화면 이름은 서버가 준다."""
    both = {"stage2": _res(2), "stage3": _res(3)}
    j = _job(stage=2, llm=True)
    j.chain = "heads"   # 막 시작 — 단계가 아직 안 적힘
    v = analysis.status(_sess({**both, "job": j}), outline=(OV, VARS), plans={})
    a = _items(v)
    assert v["job"]["what"] == "헤딩 LLM 판정 · 서식 계획" and (v["chain"]["chain"], v["chain"]["name"]) == ("heads", "헤딩 LLM 판정 · 서식 계획")
    assert (a["heads"]["llm"]["state"], a["templates"]["llm"]["state"], a["formats"]["llm"]["state"], a["tables"]["llm"]["state"]) == ("running", "running", "wait", "none")
    assert "헤딩 판정이 끝나면" in a["formats"]["llm"]["text"] and a["tables"]["state"] == "done"
    j2 = _job(stage=2, llm=True)
    j2.chain, j2.parts = "formats", [{"key": "formats", "name": "f", "no": 1, "status": "running", "msg": "T1 계획 받는 중 — 끝남 0/1"}]
    v2 = analysis.status(_sess({**both, "job": j2}), outline=(OV, VARS), plans={})
    b = _items(v2)
    assert v2["job"]["what"] == "서식 정리 계획" and v2["chain"]["running"] == ["formats"]
    assert (b["heads"]["llm"]["state"], b["tables"]["llm"]["state"], b["formats"]["llm"]["state"]) == ("none", "none", "running")
    j3 = _job(stage=2, llm=True)
    j3.chain = "llm"
    assert analysis.status(_sess({**both, "job": j3}), outline=(OV, VARS), plans={})["chain"]["name"] == "LLM 검증·보완"


def test_api_heading_llm_run_continues_into_format_plans(client, monkeypatch):
    """「헤딩 그래프(LLM)」(POST …/headings {stage: 2, llm: true}) = 헤딩 판정 → 이어서 서식 정리 계획(이어 돌리기 "heads") — 표 구조 LLM 은 안 돌고 문서는 안 바뀐다."""
    from app import llm
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    d = _upload(client, FORM)
    assert client.post(f"/api/docs/{d}/headings", json={"first": True}).status_code == 202
    _wait_heads(client, d)
    need = _items(client.get(f"/api/docs/{d}/analysis").json())["formats"]["llm"]["need"]
    assert need >= 1
    f2, f3 = _llm_ok(2), _llm_ok(3)
    monkeypatch.setattr(heading_runs, "run_stage2", f2)
    monkeypatch.setattr(heading_runs, "run_stage3", f3)
    asked = []

    def fake_call(schema, content, what, **kw):
        asked.append(what)
        return {"data": {"summary": "정리", "levels": []}, "backend": "api", "ms": 1, "costUsd": 0.0, "error": None, "model": kw.get("model"), "effort": kw.get("effort")}
    monkeypatch.setattr(llm, "call", fake_call)
    rev = server.DOCS[d].rev
    assert client.post(f"/api/docs/{d}/headings", json={"stage": 2, "llm": True, "skill": "nope"}).status_code == 404   # 서식 정리 스킬 키
    r = client.post(f"/api/docs/{d}/headings", json={"stage": 2, "llm": True})
    assert r.status_code == 202, r.text
    assert r.json()["chain"] == "heads" and r.json()["stage"] == 2
    j = _wait_job(client, d)
    assert j["status"] == "done", j
    assert (f2.calls, f3.calls, len(asked)) == (1, 0, need) and set(asked) == {"tpl-agent"} and server.DOCS[d].rev == rev
    assert j["stage"] == 2 and any(s["name"] == "서식 정리 계획 — LLM" and s["status"] == "ok" for s in j["steps"])   # 추출·설정 2단계의 진행 목록에도 보인다
    v = client.get(f"/api/docs/{d}/analysis").json()
    assert [(s["key"], s["no"], s["status"]) for s in v["chain"]["steps"]] == [("heads", 1, "ok"), ("formats", 2, "ok")] and v["chain"]["name"] == "헤딩 LLM 판정 · 서식 계획"
    f = _items(v)["formats"]["llm"]
    assert (f["state"], f["planned"], f["need"]) == ("done", need, need) and _items(v)["tables"]["llm"]["state"] == "none"
    # 다시 누름 — 사람이 그 단추를 눌렀으므로 헤딩 판정은 다시 돈다(LLM 검증·보완은 건너뛴다) · 계획은 다 있으므로(가짜 실행은 그래프를 안 바꾼다) 다시 받지 않는다
    assert client.post(f"/api/docs/{d}/headings", json={"stage": 2, "llm": True}).status_code == 202
    _wait_job(client, d)
    assert (f2.calls, len(asked)) == (2, need)
    assert [s["status"] for s in client.get(f"/api/docs/{d}/analysis").json()["chain"]["steps"]] == ["ok", "skip"]
    # 서식 계획만(헤딩 추출 탭 진행 줄 「조정」 의 「계획 받기」) — 헤딩 · 표 LLM 은 안 돈다
    r = client.post(f"/api/docs/{d}/analysis/llm", json={"only": "formats"})
    assert r.status_code == 202 and r.json()["chain"] == "formats"
    _wait_job(client, d)
    v = client.get(f"/api/docs/{d}/analysis").json()
    assert [(s["key"], s["no"], s["status"]) for s in v["chain"]["steps"]] == [("formats", 1, "skip")] and (f2.calls, f3.calls, len(asked)) == (2, 0, need)
    del server.DOCS[d].tpl_plans   # 계획이 없는 것처럼 — 서식 계획만 다시 받는다
    (__import__("app.works", fromlist=["folder"]).folder(d) / "outline_agent" / "plans.json").unlink()
    assert client.post(f"/api/docs/{d}/analysis/llm", json={"only": "formats"}).status_code == 202
    _wait_job(client, d)
    assert (f2.calls, f3.calls, len(asked)) == (2, 0, need * 2)
    assert client.post(f"/api/docs/{d}/analysis/llm", json={"only": "tables"}).status_code == 400


def test_api_heading_llm_run_ends_done_when_llm_falls_back(client, monkeypatch):
    """「헤딩 그래프(LLM)」 에서 LLM 이 답을 못 하면 전처럼 작업은 끝난 것으로(결과 = 스크립트 대체 판정) — 서식 정리 계획은 돌리지 않는다. LLM 검증·보완은 실패로 끝난다(위 시험)."""
    d = _upload(client, FORM)
    assert client.post(f"/api/docs/{d}/headings", json={"first": True}).status_code == 202
    _wait_heads(client, d)

    def fallback(sess, job, use_llm):
        st = heading_runs.state(sess)
        st["stage2"]["llm"] = {**st["stage2"]["llm"], "requested": True, "fallback": True, "error": "off"}
        return 9
    monkeypatch.setattr(heading_runs, "run_stage2", fallback)
    assert client.post(f"/api/docs/{d}/headings", json={"stage": 2, "llm": True}).status_code == 202
    j = _wait_job(client, d)
    assert j["status"] == "done" and j["error"] is None and j["run"] == 9
    v = client.get(f"/api/docs/{d}/analysis").json()
    assert [(s["key"], s["status"]) for s in v["chain"]["steps"]] == [("heads", "failed"), ("formats", "stopped")] and v["job"] is None
    assert _items(v)["heads"]["llm"]["state"] == "failed" and not any(s["name"].startswith("서식 정리 계획") for s in j["steps"])
