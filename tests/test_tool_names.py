"""도구 이름 고치기(spec_워크플로우 ② §18-19) — 저장(틀 · 줄 key 마다 이름) · 화면으로 나가는 문 셋(등록부 응답 · 실행 층의 정의 · 조립 응답)에 얹기 · 만든 글은 기본 이름 그대로 · API.
conftest 가 NFM_TOOL_NAMES 를 시험마다 임시 파일로 돌린다(사용자가 고친 이름이 줄 이름을 견주는 시험에 섞이지 않게)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import agent_notes, custom_tasks, custom_tasks_api, workflow
from app import tool_names as T
from app import tool_names_api as TA
from app import workflow_state as WS


def _client():
    app = FastAPI()
    app.include_router(TA.router)
    return TestClient(app)


def _unit(family="relay"):
    """그 틀의 도구 하나 → (줄 key, 기본 이름) — 등록부에서 읽는다(이름을 시험에 적어 두지 않는다: 줄 이름은 바뀐다)."""
    rows = TA.bases(family)
    k = next(k for k in rows if k not in T.FIXED and k != "files")
    return k, rows[k]


def test_store_keeps_a_name_per_family_and_unit():
    assert T.load() == {"version": 0, "names": {}} and T.shown("relay", "heads", "헤딩 · 표 분석") == "헤딩 · 표 분석"
    assert T.save("relay", "heads", "  구조   분석 ", base="헤딩 · 표 분석") == {"version": 1, "name": "구조 분석"} and T.path().is_file()
    assert T.shown("relay", "heads", "헤딩 · 표 분석") == "구조 분석" and T.shown("gather", "heads", "헤딩 · 표 분석") == "헤딩 · 표 분석"   # 같은 줄 key 도 틀마다 다른 도구
    assert T.names("relay") == {"heads": "구조 분석"} and T.names("single") == {} and T.names("nope") == {}
    with pytest.raises(T.Stale):
        T.save("relay", "heads", "x", expect=0)
    assert T.save("relay", "heads", "헤딩 · 표 분석", base="헤딩 · 표 분석") == {"version": 2, "name": ""} and T.load()["names"] == {}   # 기본 이름과 같으면 지운다
    assert T.save("relay", "heads", "구조 분석")["version"] == 3 and T.save("relay", "heads", "")["name"] == "" and T.load()["names"] == {}   # 빈 이름 = 기본 이름으로


def test_names_are_checked():
    for bad in ("줄\n바꿈", "「이름」", "가" * (T.NAME_MAX + 1), 3):
        with pytest.raises(ValueError):
            T.save("relay", "heads", bad)
    for fam, unit in (("nope", "heads"), ("relay", "a b"), ("relay", "hand")):   # 없는 틀 · 꼴이 틀린 key · 사람이 하는 일
        with pytest.raises(ValueError):
            T.save(fam, unit, "이름")
    assert T.load() == {"version": 0, "names": {}}


def test_broken_file_and_memory_mode(monkeypatch):
    T.path().write_text("{broken", encoding="utf-8")
    assert T.load() == {"version": 0, "names": {}} and T.names("relay") == {}
    T.path().write_text('{"version": 4, "names": {"relay.heads": "구조 분석", "relay.hand": "x", "nope.a": "y", "relay.llm": ""}}', encoding="utf-8")
    assert T.load() == {"version": 4, "names": {"relay.heads": "구조 분석"}}   # 꼴이 틀린 줄은 버린다
    monkeypatch.setenv("NFM_TOOL_NAMES", "off")
    assert T.path() is None and T.load()["names"] == {}
    assert T.save("gather", "heads", "분석")["name"] == "분석" and T.names("gather") == {"heads": "분석"}
    T.save("gather", "heads", "")


def test_apply_copies_only_when_a_line_is_renamed():
    task = workflow.BY_JOB["plan_to_report"]
    assert T.apply(task, "relay") is task   # 고친 것이 없으면 받은 것 그대로
    k, base = _unit("relay")
    T.save("relay", k, "내가 붙인 이름", base=base)
    got = T.apply(task, "relay")
    steps = {s["key"]: s for g in got["stages"] for s in g["steps"]}
    assert got is not task and steps[k]["name"] == "내가 붙인 이름" and steps[k]["baseName"] == base
    assert all("baseName" not in s for key, s in steps.items() if key != k)
    assert {s["key"]: s["name"] for g in task["stages"] for s in g["steps"]}[k] == base   # 등록부는 그대로
    assert T.apply(task, "gather") is task and T.apply(None, "relay") is None


def test_every_screen_door_shows_the_new_name_and_made_texts_keep_the_base():
    k, base = _unit("relay")
    md, doc = workflow.markdown(), workflow.task_markdown("plan_to_report")
    T.save("relay", k, "내가 붙인 이름", base=base)
    # ① 등록부 응답 — 붙박이 이관의 그 줄 · 단계(일반 단계)의 그 줄
    L = workflow.listing()
    step = next(s for t in L["tasks"] if t["job"] == "plan_to_report" for g in t["stages"] for s in g["steps"] if s["key"] == k)
    assert step["name"] == "내가 붙인 이름" and step["baseName"] == base
    common = [s for c in L["common"] if c["kind"] == "stage" for s in c["steps"] if s["key"] == k]
    assert common and all(s["name"] == "내가 붙인 이름" and s["baseName"] == base for s in common)
    other = next(s for t in L["tasks"] if t["job"] == "plan_merge" for g in t["stages"] for s in g["steps"])
    assert other["baseName"] == ""   # 안 고친 줄 · 다른 틀
    # ② 실행 층이 읽는 정의 — 실행 상태 · 실행 기록의 줄 이름
    line = next(x for x in WS.lines(WS.definition("plan_to_report")) if x["key"] == k)
    assert line["name"] == "내가 붙인 이름"
    # ③ 조립 응답 — 카드 · 넣기 고르기 · 도구 설명
    u = next(u for u in custom_tasks_api.tasks_get("2")["units"] if u["key"] == k)
    assert u["name"] == "내가 붙인 이름" and u["base"] == base
    # 조립한 워크플로우(이관형)도 같은 도구를 쓴다
    c = custom_tasks.create({"name": "내 이관", "source": "plan", "target": "report", "assign": {"source": ["stage_review"], "target": list(custom_tasks.STAGES)}}, [])
    mine = {s["key"]: s["name"] for g in WS.definition(c["key"])["stages"] for s in g["steps"]}
    assert mine[k] == "내가 붙인 이름"
    # 만든 글 · 등록부 · 프롬프트의 도구 표는 기본 이름 그대로
    assert workflow.markdown() == md and workflow.task_markdown("plan_to_report") == doc
    assert agent_notes.tool_map()["relay"][k]["name"] == base
    T.save("relay", k, "")
    assert next(x for x in WS.lines(WS.definition("plan_to_report")) if x["key"] == k)["name"] == base


def test_single_and_gather_units_follow_their_own_family():
    picked = {}
    for fam in ("gather", "single"):
        first = next(u for u in custom_tasks_api.tasks_get("2")["byShape"][fam]["units"] if u["key"] not in T.FIXED)   # 조립 화면에 놓을 수 있는 그 틀의 도구 하나
        k, base = first["key"], first["base"]
        assert first["name"] == base and TA.bases(fam)[k] == base
        T.save(fam, k, f"{fam} 이름", base=base)
        u = next(u for u in custom_tasks_api.tasks_get("2")["byShape"][fam]["units"] if u["key"] == k)
        assert u["name"] == f"{fam} 이름" and u["base"] == base
        picked[fam] = k
    k = picked["single"]
    names = custom_tasks_api.tasks_get("2")["byShape"]["single"]["names"]
    assert all(by[k] == "single 이름" for by in names.values() if k in by)   # 문서 종류마다의 이름 표도 고친 이름으로(도구 하나 = 이름 하나)
    bases = custom_tasks_api.tasks_get("2")["byShape"]["single"]["baseNames"]
    assert set(bases) == set(names) and all(bases[kind][k] != "single 이름" for kind in bases if k in bases[kind])


def test_api_roundtrip():
    cl, (k, base) = _client(), _unit("relay")
    assert cl.get("/api/tool-names").json() == {"version": 0, "names": {}, "max": T.NAME_MAX}
    r = cl.put(f"/api/tool-names/relay/{k}", json={"name": " 새 이름 ", "version": 0})
    also = [f for f in ("gather", "single") if (TA.bases(f) or {}).get(k) == base]   # 줄 key · 기본 이름이 같은 다른 틀의 같은 도구 — 같이 고친다
    assert r.status_code == 200 and r.json() == {"family": "relay", "unit": k, "name": "새 이름", "base": base, "shown": "새 이름", "same": [], "also": also, "version": 1}
    assert cl.get("/api/tool-names").json()["names"] == {f"{f}.{k}": "새 이름" for f in ("relay", *also)}
    assert cl.put(f"/api/tool-names/relay/{k}", json={"name": "x", "version": 0}).status_code == 409
    assert cl.put(f"/api/tool-names/relay/{k}", json={"name": "「x」"}).status_code == 400
    assert cl.put(f"/api/tool-names/relay/{k}", json={"name": "x", "version": "1"}).status_code == 400
    assert cl.put("/api/tool-names/relay/nope", json={"name": "x"}).status_code == 404
    assert cl.put(f"/api/tool-names/nope/{k}", json={"name": "x"}).status_code == 404
    assert cl.put("/api/tool-names/relay/hand", json={"name": "x"}).status_code in (400, 404)
    other = next(key for key in TA.bases("relay") if key not in (k, "files") and key not in T.FIXED)
    r = cl.put(f"/api/tool-names/relay/{other}", json={"name": "새 이름"})   # 같은 틀의 다른 도구와 같은 이름 — 막지 않고 알린다
    assert r.status_code == 200 and r.json()["same"] == [base]
    r = cl.delete(f"/api/tool-names/relay/{k}")
    assert r.status_code == 200 and r.json()["name"] == "" and r.json()["shown"] == base
    assert not any(key.endswith(f".{k}") for key in cl.get("/api/tool-names").json()["names"])   # 같이 고친 틀도 같이 되돌린다


def test_the_same_tool_in_another_family_is_renamed_together():
    cl = _client()
    twin = next(((k, b) for k, b in TA.bases("relay").items() if TA.bases("gather").get(k) == b and k not in T.FIXED), None)
    assert twin, "이관형 · 취합형이 같이 쓰는 줄(줄 key · 기본 이름이 같음)이 등록부에 있어야 한다 — 없어졌으면 이 시험과 ② §18-19 「같은 도구 — 다른 틀에도」 를 다시 본다"
    k, base = twin
    r = cl.put(f"/api/tool-names/gather/{k}", json={"name": "같이 바뀌는 이름"})
    assert r.status_code == 200 and "relay" in r.json()["also"]
    assert T.shown("relay", k, base) == T.shown("gather", k, base) == "같이 바뀌는 이름"
    diff = next(((k2, b2) for k2, b2 in TA.bases("relay").items() if k2 in TA.bases("gather") and TA.bases("gather")[k2] != b2), None)   # 줄 key 는 같아도 기본 이름이 다르면 다른 도구
    if diff:
        r = cl.put(f"/api/tool-names/relay/{diff[0]}", json={"name": "이관만"})
        assert "gather" not in r.json()["also"] and T.shown("gather", diff[0], "x") == "x"
