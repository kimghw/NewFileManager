"""조립 폼의 「1」 문서 하나(spec_워크플로우 ② §18-13 걸음 6 — 2026-11-20 사용자 「그리고 문서 하나는 왜 안되냐?」 → 답 「조립한 것만 서버로」) — 서버 쪽 조립 길:
정의(원본 없는 문서 짝) · 조립 검사 · 고를 줄 API · 정의 → 워크플로우 짓기 · 앱이 그 틀을 알아보기 · 서버가 맡는 조건.
스위치 둘(custom_tasks.SINGLE_OPEN · workflow_state.OPEN_CUSTOM)은 운영에서 꺼 둔 채다 — 시험은 켜서 본다(monkeypatch). 실행기의 처리 함수는 tests/test_workflow_single.py."""
import json
import time

import pytest
from fastapi.testclient import TestClient

import merge_data as M
from app import custom_tasks as C
from app import custom_tasks_api as CA
from app import job_prompts, server, task_options, unit_steps, workflow, workflow_runs, works
from app import workflow_exec as X
from app import workflow_state as S
from app import workflow_units as U

SOON = "문서 하나 워크플로우는 아직 조립할 수 없습니다"
PLAN = [("프로젝트 구성", ["read", "load", "values", "review", "plan", "apply"]), ("헤딩 추출", ["heads", "headsLlm", "adjust", "tree"]), ("표", ["tables", "tablesLlm", "tableTools"])]
REPORT = [("프로젝트 구성", ["values", "review"]), ("구조 반영", ["plan", "apply"])]


@pytest.fixture
def on(monkeypatch):
    """조립의 스위치를 켠다(「1」 문서 하나를 조립할 수 있다) — 서버가 맡는 스위치(OPEN_CUSTOM)는 그것을 보는 시험이 따로 켠다."""
    monkeypatch.setattr(C, "SINGLE_OPEN", True)


@pytest.fixture
def client():
    yield TestClient(server.app)


def _L(*units):
    """문서 하나의 줄들 — 하는 문서는 적지 않는다(그 문서가 곧 목적 문서)."""
    return [{"unit": u} for u in units]


def _one(*units, name="a"):
    return [{"name": name, "steps": _L(*units)}]


def _names(flow):
    return [(g["name"], [s["unit"] for s in g["steps"]]) for g in flow]


def _make(kind="plan", flow=None, name="문서 하나"):
    return C.create({"name": name, "shape": "single", "source": "", "target": kind, "flow": flow or CA.single_lines(kind)}, ["사업계획서 취합"])


def test_the_switches_are_on_and_turning_them_off_refuses_like_before(client, monkeypatch):
    """스위치 둘은 켜져 있다(2026-11-20 통합 — 사용자 답 「조립한 것만 서버로」) · OPEN 에는 single 이 없다(붙박이는 화면 그대로).
    꺼 보면 전처럼 「준비 중」(틀의 soon 글 · 검사 · 만들기의 거절) · 켜면 soon 이 빈 글(soon 을 읽는 곳은 shape_soon 하나)."""
    assert C.SINGLE_OPEN is True and S.OPEN_CUSTOM == {"single"} and "single" not in S.OPEN   # OPEN 에 single 을 넣지 않는다(붙박이가 같이 열린다)
    monkeypatch.setattr(C, "SINGLE_OPEN", False)
    assert C.shape_soon("single").startswith(SOON) and C.shape_soon("relay") == C.shape_soon("gather") == C.shape_soon("nope") == ""
    assert {s["id"]: bool(s["soon"]) for s in C.shapes()} == {"single": True, "relay": False, "gather": False}
    flow = CA.single_lines("plan")
    assert C.check("single", "", "plan", flow)["errors"][0].startswith(SOON) and C.check("single", "plan", "report", flow)["errors"][0].startswith(SOON)
    for body in ({"name": "하나", "shape": "single", "source": "", "target": "plan", "flow": flow}, {"name": "하나", "shape": "single", "source": "", "target": "plan", "assign": {"target": ["stage_review"]}}):
        with pytest.raises(ValueError, match=SOON):
            C.create(body)
        r = client.post("/api/tasks", json=body)
        assert r.status_code == 400 and r.json()["detail"].startswith(SOON)
    assert C.all() == []
    v = client.get("/api/tasks?v=2").json()
    assert {s["id"]: bool(s["soon"]) for s in v["shapes"]} == {"single": True, "relay": False, "gather": False}
    assert client.post("/api/tasks/check", json={"shape": "single", "flow": flow}).json()["errors"][0].startswith(SOON)
    monkeypatch.setattr(C, "SINGLE_OPEN", True)
    assert C.shape_soon("single") == "" and [s["soon"] for s in C.shapes()] == ["", "", ""] and [s["soon"] for s in client.get("/api/tasks?v=2").json()["shapes"]] == ["", "", ""]
    assert all(s["soon"] for s in C.SHAPES if s["id"] == "single")   # 틀의 글 자체는 그대로(스위치가 가린다)
    assert C.check("single", "", "plan", flow)["errors"] == []


def test_the_lines_of_a_single_document_follow_the_unit_table_and_the_registry():
    """놓을 수 있는 줄 = 문서 하나 가족의 단위에서 맨 앞 묶음에 저절로 서는 「준비」 를 뺀 것 + 「사람이 하는 일」 — 차례는 등록부 「사업계획서 양식 표준화」 의 줄 차례. 문서 짝 = 원본 없이 목적 종류 하나."""
    order = [s["key"] for g in workflow.BY_JOB["plan_fit"]["stages"] for s in g["steps"] if s["key"] not in C.SINGLE_AUTO]
    assert list(C.SINGLE_UNITS) == [*order, "hand"] and set(C.SINGLE_UNITS) - {"hand"} == set(U.SINGLE) - set(C.SINGLE_AUTO) and C.SINGLE_AUTO == ("open",)
    assert C.auto_units("single") == ("open",) and C.auto_units("relay") == C.auto_units("gather") == C.auto_units() == C.AUTO_UNITS == ("files",)
    assert all(U.SINGLE[k]["server"] for k in C.SINGLE_UNITS if k != "hand") and "hand" not in U.SINGLE and U.COMMON["hand"]["server"]
    # 사실 → 그것을 주는 줄 — 단위의 needs · gives 와 맞는다(준비가 주는 slots 는 뺀다)
    assert all(f in U.SINGLE[k]["gives"] for f, k in C.SINGLE_NEED.items()) and {f for u in U.SINGLE.values() for f in u["needs"]} - {"slots"} == set(C.SINGLE_NEED)
    uses = {k: C.uses_of(U.SINGLE[k], "single") for k in U.SINGLE}
    assert uses["apply"] == uses["plan"] == [{"unit": "values", "must": False}] and uses["headsLlm"] == [{"unit": "heads", "must": False}] and uses["adjust"] == [{"unit": "headsLlm", "must": False}]
    assert uses["tablesLlm"] == [{"unit": "tables", "must": False}] and not any(uses[k] for k in ("open", "read", "load", "values", "review", "heads", "tree", "tables", "tableTools"))
    assert C.uses_of(U.COMMON["hand"], "single") == []
    # 문서 짝 · 그 종류의 붙박이
    assert C.pairs_of("single") == C.SINGLE_PAIRS == (("", "plan"), ("", "report")) and C.pairs_of("relay") == C.PAIRS and C.pairs_of("gather") == C.GATHER_PAIRS and C.pairs_of("nope") == C.PAIRS
    assert C.SINGLE_BASE == {"plan": "plan_fit", "report": "report_fit"} and set(C.SINGLE_BASE) == {b for _a, b in C.SINGLE_PAIRS}
    for kind, job in C.SINGLE_BASE.items():
        t = workflow.BY_JOB[job]
        assert t["units"] == "single" and [(r["role"], r["kind"]) for r in t["roles"]] == [("target", kind)], job
    assert [x["id"] for x in next(s for s in C.SHAPES if s["id"] == "single")["slots"][0]["kinds"]] == ["plan", "report"] and C.family_of("single") == "single"
    # 줄 이름 — 그 문서 종류의 붙박이 줄 이름이 먼저(연차보고서 = 양식 맞추기의 이름) · 거기 없는 줄은 양식 표준화의 것
    p, r = C.unit_names("single"), C.unit_names("single", "report")
    assert p == C.unit_names("single", "plan") and (p["values"], p["apply"]) == ("프로젝트 구성 추출", "적용(문서에 반영)") and (r["values"], r["apply"]) == ("프로젝트 구성 값 정하기", "반영")
    assert r["heads"] == p["heads"] == "헤딩 · 템플릿 추출" and p["hand"] == r["hand"] == "사람이 하는 일" and set(C.SINGLE_UNITS) <= set(p) and set(C.SINGLE_UNITS) <= set(r)
    assert C.unit_names()["heads"] == "헤딩 · 표 분석" and C.unit_names("gather")["frame"]   # 다른 틀의 이름은 그대로


def test_check_takes_only_the_single_lines_in_an_order_that_can_run(on):
    """조립 검사 — 그 종류의 처음 줄 목록은 그대로 통과 · 놓을 수 없는 줄(같이 쓰는 단위 · 이관 · 취합의 줄 · 준비) · 차례가 거꾸로 = 거절 / 만드는 줄이 없음 · 같은 줄 두 번 · 유료 · 문서 바뀜 = 경고."""
    for kind, want in (("plan", PLAN), ("report", REPORT)):
        got = C.check("single", "", kind, CA.single_lines(kind))
        assert got["errors"] == [] and got["std"] is None and _names(got["flow"]) == want and [g["id"] for g in got["flow"]] == [f"g{i + 1}" for i in range(len(want))], (kind, got)
        assert all(s == {"unit": s["unit"], "on": []} for g in got["flow"] for s in g["steps"])   # 줄의 on 은 늘 빈 목록 · 다른 칸이 없다
    got = C.check("single", "", "plan", CA.single_lines("plan"))
    assert got["warns"] == ["유료 LLM 을 부르는 줄: 헤딩 LLM 판정 · 서식 계획 · 표 판정(LLM) — 라벨 검증 · 보완",
                            "「조정 — 템플릿 조정 · 서식 조정」 은 서식 정리 계획을 받지 않은 템플릿이 남아 있으면 그 계획을 다시 받습니다(유료 LLM)",
                            "문서를 바꾸는 줄: 적용(문서에 반영) · 조정 — 템플릿 조정 · 서식 조정"], got["warns"]   # 손으로 하는 줄(템플릿 관계 · 표 점검)은 사람이 할 때만 바뀐다
    assert C.check("single", "", "report", CA.single_lines("report"))["warns"] == ["문서를 바꾸는 줄: 반영"]   # 그 종류의 줄 이름으로
    # 놓을 수 없는 줄 — 같이 쓰는 단위로 새지 않는다(자동 확정 config · 이관의 구조 반영 division · 작성요령 삭제 guide …) · 이관 · 취합의 줄 · 준비
    for k in ("config", "configLoad", "division", "reheads", "reheadsLlm", "guide", "link", "llm", "gaps", "tableMap", "frame", "part", "drop", "files", "nope"):
        errs = C.check("single", "", "plan", _one("values", k))["errors"]
        assert errs == [f"놓을 수 없는 줄입니다 — {k}"], (k, errs)
    assert C.check("single", "", "plan", _one("open", "values"))["errors"] == ["놓을 수 없는 줄입니다 — 문서 올리기 · 첫 분석 (맨 앞 묶음에 저절로 섭니다)"]
    assert all(U.unit(k, "single") is U.COMMON[k] for k in ("config", "division", "guide"))   # 단위 찾기는 같이 쓰는 것으로 넘어간다 — 조립 검사가 막는다
    # 차례가 거꾸로 — 그 줄이 기대는 것을 만드는 줄이 정의 안에 있는데 뒤에만 있다
    for flow, word in ((_one("apply", "values"), "「적용(문서에 반영)」 은 「프로젝트 구성 추출」 뒤에 와야 합니다"), (_one("plan", "values"), "「변경 계획 보기」 는 「프로젝트 구성 추출」 뒤에 와야 합니다"),
                       (_one("headsLlm", "heads"), "「헤딩 LLM 판정 · 서식 계획」 은 「헤딩 · 템플릿 추출」 뒤에 와야 합니다"), (_one("heads", "adjust", "headsLlm"), "「조정 — 템플릿 조정 · 서식 조정」 은 「헤딩 LLM 판정 · 서식 계획」 뒤에 와야 합니다"),
                       (_one("tablesLlm", "tables"), "「표 판정(LLM) — 라벨 검증 · 보완」 은 「표 구조 — 칸 역할 라벨」 뒤에 와야 합니다"),
                       ([{"name": "a", "steps": _L("apply")}, {"name": "b", "steps": _L("values")}], "뒤에 와야 합니다")):   # 묶음을 건너서도
        assert word in " / ".join(C.check("single", "", "plan", flow)["errors"]), (flow, C.check("single", "", "plan", flow)["errors"])
    assert C.check("single", "", "report", _one("apply", "values"))["errors"] == ["「반영」 은 「프로젝트 구성 값 정하기」 뒤에 와야 합니다"]
    # 그 밖의 차례는 자유 — 헤딩 · 표의 줄을 프로젝트 구성보다 앞에(붙박이의 묶음 규칙과 같다) · 연차보고서에도 헤딩 · 표 줄 · 원본 문서를 쓰는 줄은 보지 않는다
    free = [{"name": "헤딩", "steps": _L("heads", "headsLlm", "adjust")}, {"name": "표", "steps": _L("tables", "tablesLlm")}, {"name": "구성", "steps": _L("values", "apply")}]
    assert C.check("single", "", "plan", free)["errors"] == [] and C.check("single", "", "report", free)["errors"] == [] and C.check("single", "", "plan", _one("tree"))["errors"] == []
    # 만드는 줄이 정의에 없으면 경고(저장은 됨) — 실행기가 하는 줄만(사람이 보는 「변경 계획 보기」 는 아니다)
    for flow, word in ((_one("apply"), "이 워크플로우에는 「프로젝트 구성 추출」 이 없습니다 — 시작할 때 이미 되어 있어야 하고, 아니면 「적용(문서에 반영)」 에서 멈추거나 그 줄을 하지 않고 남깁니다"),
                       (_one("headsLlm"), "이 워크플로우에는 「헤딩 · 템플릿 추출」 이 없습니다"), (_one("heads", "adjust"), "이 워크플로우에는 「헤딩 LLM 판정 · 서식 계획」 이 없습니다"),
                       (_one("tablesLlm"), "이 워크플로우에는 「표 구조 — 칸 역할 라벨」 이 없습니다")):
        got = C.check("single", "", "plan", flow)
        assert got["errors"] == [] and any(w.startswith(word) for w in got["warns"]), (flow, got)
    assert not any("없습니다" in w for w in C.check("single", "", "plan", _one("plan"))["warns"]) and not any("없습니다" in w for w in C.check("single", "", "plan", CA.single_lines("plan"))["warns"])
    # 같은 줄을 두 번 넘게 — 거절이 아니라 경고(뒤의 줄은 그 차례에 다시 본다)
    twice = C.check("single", "", "plan", _one("heads", "headsLlm", "heads"))
    assert twice["errors"] == [] and "「헤딩 · 템플릿 추출」 을 두 번 넘게 놓았습니다" + C.AGAIN in twice["warns"]
    # 꼴 — 줄의 on 은 받은 것을 버리고 빈 목록 · 같은 차례(beside) · 줄의 칸(col)은 지운다 · 사람이 하는 일은 줄 id · 이름 · 글을 지닌다
    got = C.check("single", "", "plan", [{"name": " 구성 ", "steps": [{"unit": "values", "on": ["target"], "col": "source"}, {"unit": "apply", "on": ["source", "target"], "beside": True},
                                                                   {"unit": "hand", "on": ["target"], "name": "결과  확인", "note": "표를 훑어봅니다", "beside": True}]}])
    assert got["errors"] == [] and got["flow"] == [{"id": "g1", "name": "구성", "steps": [{"unit": "values", "on": []}, {"unit": "apply", "on": []},
                                                                                         {"unit": "hand", "on": [], "id": "hand1", "name": "결과 확인", "note": "표를 훑어봅니다", "tool": ""}]}]
    assert C.check("single", "", "plan", _one("hand", "hand"))["errors"] == [] and [s["id"] for s in C.check("single", "", "plan", _one("hand", "hand"))["flow"][0]["steps"]] == ["hand1", "hand2"]
    assert C.check("single", "", "plan", [{"name": "a", "steps": [{"unit": "heads", "on": ["x"]}]}])["errors"] == ["줄의 「하는 문서」 꼴이 틀립니다"] and C.check("single", "", "plan", "x")["errors"] == ["묶음을 하나 이상 두세요"]
    assert any("줄이 없습니다" in e for e in C.check("single", "", "plan", [{"name": "빈 묶음", "steps": []}, {"name": "b", "steps": _L("heads")}])["errors"])
    # 문서 짝 — 원본이 없다(빈 글) · 목적 = 사업계획서 | 연차보고서
    pair = "문서 하나 워크플로우의 목적 문서는 사업계획서 · 연차보고서 가운데 하나입니다(원본 문서는 없습니다)"
    for src, dst in (("plan", "report"), ("", "part"), ("part", "plan"), (None, "plan"), ("", "")):
        assert C.check("single", src, dst, _one("heads"))["errors"] == [pair], (src, dst)
    assert not any("원본 문서를 쓰는 줄" in e for flow in (free, _one("heads"), _one("tree")) for e in C.check("single", "", "plan", flow)["errors"])
    # 다른 틀은 그대로 — 문서 하나의 줄을 이관형 · 취합형에 놓지 못하고, 문서 짝의 글도 그 틀의 것
    assert any("놓을 수 없는 줄" in e for e in C.check("relay", "plan", "report", _one("values"))["errors"]) and any("놓을 수 없는 줄" in e for e in C.check("gather", "part", "plan", _one("adjust"))["errors"])
    assert any("문서 쌍은 사업계획서 → 연차보고서" in e for e in C.check("relay", "", "plan", _one("values"))["errors"])


def test_create_read_update_delete_keep_the_single_shape(on):
    """만들기 → 다시 읽기 → 고치기 → 지우기 — 늘 줄 목록(v2)으로 저장 · 원본은 빈 글 · 줄의 on 은 빈 목록 · 지문은 틀 · 문서 종류 · 줄에서."""
    t = _make("plan", [{"name": "구성", "steps": [{"unit": "values", "on": ["target"]}, {"unit": "apply", "beside": True, "col": "source"}, {"unit": "hand", "name": "확인"}]}, {"name": "헤딩", "steps": _L("heads", "headsLlm", "adjust")}])
    key = t["key"]
    assert (t["shape"], t["v"], t["source"], t["target"], t["assign"], t["stages"]) == ("single", 2, "", "plan", None, []) and [g["id"] for g in t["flow"]] == ["g1", "g2"]
    row = json.loads(C.path().read_text(encoding="utf-8"))["tasks"][0]
    assert (row["shape"], row["v"], row["source"], row["target"]) == ("single", 2, "", "plan") and "assign" not in row and "stages" not in row
    assert row["flow"][0]["steps"] == [{"unit": "values", "on": []}, {"unit": "apply", "on": []}, {"unit": "hand", "on": [], "id": "hand1", "name": "확인", "note": "", "tool": ""}]
    assert C.get(key) == t and C.all() == [t]
    # 앱이 그 틀로 알아본다 — 조립한 문서 하나 · 원본 없음 · 목적 종류 · 그 종류의 붙박이
    assert C.is_single(key) and not C.is_gather(key) and C.is_key(key) and C.source_file(key) is None and C.target_file(key) == "plan" and works.TARGET_FILE.get(key) == "plan"
    assert not C.is_single("plan_fit") and not C.is_single("report_fit") and not C.is_single("u_00000000") and C.source_file("plan_to_report") == "plan" and C.target_file("plan_fit") is None
    assert C.base_of(t) == "plan_fit" and C.base_of({**t, "target": "report"}) == "report_fit" and C.base_of({"shape": "gather"}) == "plan_merge" and C.base_of({"shape": "relay"}) == C.base_of(None) == C.BASE
    assert not workflow_runs._relay_made(key) and not workflow_runs._relay_made("plan_to_report") and task_options._zones_default(key) == [] and job_prompts.get(key) is None   # 이관의 전제를 물려받지 않는다
    # 지문 — 묶음 이름 · 사람이 하는 일의 글은 밖 · 줄 · 문서 종류 · 틀은 안
    sig = C.sig(t)
    assert sig == C.sig({**t, "name": "다른 이름", "flow": [{**g, "name": g["name"] + "!"} for g in t["flow"]]}) and sig != C.sig({**t, "target": "report"}) and sig != C.sig({**t, "shape": "relay"})
    assert sig != C.sig({**t, "flow": [t["flow"][0], {**t["flow"][1], "steps": t["flow"][1]["steps"][:2]}]})
    # 고치기 — 이름 · 글만(지문 그대로) · 줄(지문이 바뀐다) · 쓰는 중이면 줄은 못 바꾼다 · 문서 짝 · 틀 · 옛 꼴로는 못 고친다
    u = C.update(key, {"name": "구조와 헤딩", "desc": "표는 안 함", "premise": "값은 문서에서만"})
    assert (u["name"], u["desc"], u["premise"]) == ("구조와 헤딩", "표는 안 함", "값은 문서에서만") and C.sig(u) == sig and u["flow"] == t["flow"] and job_prompts.get(key)["text"] == "값은 문서에서만"   # 적은 전제는 그 글
    u = C.update(key, {"flow": [{"name": "구성", "steps": _L("values", "apply")}, {"name": "표", "steps": _L("tables", "tablesLlm")}]})
    assert _names(u["flow"]) == [("구성", ["values", "apply"]), ("표", ["tables", "tablesLlm"])] and C.sig(u) != sig and u["shape"] == "single" and u["source"] == ""
    with pytest.raises(C.Refused, match="단계를 바꿀 수 없습니다"):
        C.update(key, {"flow": [{"name": "구성", "steps": _L("values")}]}, busy=1)
    assert C.update(key, {"name": "이름만"}, busy=1)["name"] == "이름만"
    for body, word in (({"source": "plan"}, "문서 쌍은 고칠 수 없습니다"), ({"target": "report"}, "문서 쌍은 고칠 수 없습니다"), ({"shape": "relay"}, "틀은 고칠 수 없습니다"),
                       ({"flow": [{"name": "a", "steps": _L("config")}]}, "놓을 수 없는 줄"), ({"flow": [{"name": "a", "steps": _L("apply", "values")}]}, "뒤에 와야 합니다")):
        with pytest.raises(ValueError, match=word):
            C.update(key, body)
    with pytest.raises(C.Refused, match="줄 목록으로 조립한 것"):
        C.update(key, {"assign": {"source": [], "target": ["stage_fill"]}})
    # 만들 때의 거절 — 옛 꼴(assign)로는 못 만든다 · 다른 문서 짝 · 이름 겹침
    for body, word in (({"name": "옛 꼴", "shape": "single", "source": "", "target": "plan", "stages": ["stage_review"]}, "줄 목록으로 조립합니다"),
                       ({"name": "짝", "shape": "single", "source": "plan", "target": "report", "flow": _one("heads")}, "목적 문서는 사업계획서 · 연차보고서 가운데 하나"),
                       ({"name": "짝", "shape": "single", "target": "part", "flow": _one("heads")}, "목적 문서는"), ({"name": "이름만", "shape": "single", "flow": _one("heads")}, "이미 있는"),
                       ({"name": "거꾸로", "shape": "single", "flow": _one("apply", "values")}, "뒤에 와야 합니다"), ({"name": "사업계획서 취합", "shape": "single", "flow": _one("heads")}, "이미 있는")):
        with pytest.raises(ValueError, match=word):
            C.create(body, ["사업계획서 취합"])
    d = C.create({"name": "기본 짝", "shape": "single", "flow": _one("heads")})   # 문서 짝을 안 보내면 그 틀의 첫 짝(원본 없음 → 사업계획서)
    assert (d["source"], d["target"]) == ("", "plan")
    assert C.delete(key) and not C.delete(key) and C.delete(d["key"]) and C.all() == [] and not C.is_single(key)


def test_a_stored_single_definition_keeps_its_shape_and_is_never_assembled_as_a_relay(on, monkeypatch):
    """저장본의 틀은 보존된다 — 스위치를 꺼도 읽히고(문서 하나로 지어진다 · 이관형으로 짓지 않는다) 줄은 못 고친다 / 꼴이 틀린 줄(문서 하나인데 이관의 짝 · 이관형인데 원본이 빈 글)은 숨기되 읽은 그대로 남긴다."""
    t = _make("report", [{"name": "구성", "steps": _L("values", "apply")}])
    monkeypatch.setattr(C, "SINGLE_OPEN", False)
    got = C.get(t["key"])
    assert got == t and got["shape"] == "single" and C.is_single(t["key"])
    task = workflow.assemble(got)
    assert task["units"] == "single" and [r["role"] for r in task["roles"]] == ["target"] and [s["key"] for s in task["stages"][0]["steps"]] == ["open", "values", "apply"]
    assert C.update(t["key"], {"name": "이름은 고친다"})["name"] == "이름은 고친다"
    with pytest.raises(ValueError, match=SOON):
        C.update(t["key"], {"flow": [{"name": "구성", "steps": _L("values")}]})
    with pytest.raises(ValueError, match=SOON):
        _make("plan", name="새로는 못 만든다")
    # 손으로 적은 줄들 — 맞는 것 하나 · 꼴이 틀린 것 둘
    rows = [{"key": "u_0000000a", "name": "맞음", "source": "", "target": "plan", "shape": "single", "v": 2, "flow": [{"id": "g1", "name": "헤딩", "steps": [{"unit": "heads", "on": ["target"], "beside": True}]}]},
            {"key": "u_0000000b", "name": "이관의 짝", "source": "plan", "target": "report", "shape": "single", "v": 2, "flow": [{"id": "g1", "name": "헤딩", "steps": [{"unit": "heads", "on": []}]}]},
            {"key": "u_0000000c", "name": "원본이 빈 이관", "source": "", "target": "report", "shape": "relay", "v": 2, "flow": [{"id": "g1", "name": "헤딩", "steps": [{"unit": "heads", "on": ["target"]}]}]}]
    C.path().write_text(json.dumps({"version": 3, "tasks": rows}, ensure_ascii=False), encoding="utf-8")
    assert [x["key"] for x in C.all()] == ["u_0000000a"] and C.get("u_0000000a")["flow"][0]["steps"] == [{"unit": "heads", "on": []}]   # 읽을 때도 on 은 빈 목록 · 같은 차례는 지운다
    assert workflow.assemble(C.get("u_0000000a"))["units"] == "single" and workflow.task_of("u_0000000b") is None
    C.update("u_0000000a", {"name": "맞음 2"})
    assert [r["key"] for r in json.loads(C.path().read_text(encoding="utf-8"))["tasks"]] == ["u_0000000a", "u_0000000b", "u_0000000c"]   # 숨은 줄은 읽은 그대로 남는다


def test_the_registry_builds_a_single_family_workflow_from_the_definition(on, monkeypatch):
    """정의 → 등록부 꼴: 가족 single · 목적 역할 하나(그 종류의 붙박이의 것) · 맨 앞 줄 「준비」 · 줄의 글은 그 종류의 붙박이 줄 · on 은 빈 글 · 사람이 하는 일 · 한 줄 설명 · 전제."""
    flow = [{"name": "구성", "steps": _L("values", "plan", "apply") + [{"unit": "hand", "name": "구조 확인", "note": "늘어난 절을 훑어봅니다", "tool": "division"}]}, {"name": "헤딩", "steps": _L("heads", "headsLlm", "adjust")}]
    for kind, job, doc in (("plan", "plan_fit", "사업계획서"), ("report", "report_fit", "연차보고서")):
        c = _make(kind, flow, name=f"{doc} 하나")
        task, base = S.definition(c["key"]), workflow.BY_JOB[job]
        made = {s["key"]: s for g in base["stages"] for s in g["steps"]}
        std = {s["key"]: s for g in workflow.BY_JOB["plan_fit"]["stages"] for s in g["steps"]}
        assert (task["job"], task["custom"], task["v"], task["units"], task["premise_from"], task.get("base")) == (c["key"], True, 2, "single", job, None)
        assert task["roles"] == tuple(dict(r) for r in base["roles"]) and task["entry"] == base["entry"] and (task["inputs"], task["output"]) == (base["inputs"], base["output"]) and "ways" not in task
        assert task["note"] == "줄 목록으로 조립한 문서 하나 워크플로우입니다 — 정한 차례대로 서버에서 진행합니다."
        assert [(g["id"], g["no"], g["name"], g["module"], [s["key"] for s in g["steps"]]) for g in task["stages"]] == [("g1", "1단계", "구성", None, ["open", "values", "plan", "apply", "hand1"]),
                                                                                                                   ("g2", "2단계", "헤딩", None, ["heads", "headsLlm", "adjust"])]
        steps = {s["key"]: s for g in task["stages"] for s in g["steps"]}
        assert all(s["on"] == "" and not s.get("beside") for s in steps.values())   # 붙박이 문서 하나처럼 — 그 문서가 곧 목적 문서
        assert all(steps[k] == made[k] for k in ("open", "values", "plan", "apply")) and all(steps[k] == std[k] for k in ("heads", "headsLlm", "adjust"))   # 줄의 글 = 그 종류의 붙박이 줄 · 없는 줄은 양식 표준화의 것
        h = steps["hand1"]
        assert (h["name"], h["by"], h["uses"]) == ("구조 확인", ("human",), ("division",)) and h["does"].startswith("늘어난 절을 훑어봅니다 — 마친 뒤")
        assert task["stages"][0]["does"] == f"{made['values']['name']} › 변경 계획 보기 › {made['apply']['name']} › 구조 확인 · 문서가 바뀜"
        assert S.family(task) == "single" and S.framed(task) and S.base(task) == "target" and S.need(task) == ["target"] and S.sig(task) == C.sig(c)   # 조립한 문서 하나는 서버가 맡는다(OPEN_CUSTOM — 2026-11-20 켬): 재료를 읽을 문서 = 그 문서
        lines = {x["key"]: x for x in S.lines(task)}
        assert all(lines[k]["unit"] is U.SINGLE[k] for k in ("open", "values", "plan", "apply", "heads", "headsLlm", "adjust")) and lines["hand1"]["unit"] is U.COMMON["hand"]
        assert all(S.roles_on(task, x["on"]) == ("target",) for x in lines.values())
        assert workflow.custom_desc(c) == f"{doc} 하나의 절 · 표 행 · 표 열을 프로젝트 구성에 맞추고 헤딩 · 템플릿을 뽑아 서식을 템플릿에 맞춥니다 — 정한 차례대로 진행합니다." == task["desc"]
        assert workflow.picked_line(c) == (f"이 워크플로우는 줄 목록으로 조립한 것 — 정한 차례: [구성: 「{made['values']['name']}」 › 「변경 계획 보기」 › 「{made['apply']['name']}」 › 「구조 확인」 / "
                                           "헤딩: 「헤딩 · 템플릿 추출」 › 「헤딩 LLM 판정 · 서식 계획」 › 「조정 — 템플릿 조정 · 서식 조정」] · 전제의 단계 설명 가운데 이 차례에 없는 일은 하지 않는다.")
        md = workflow.task_markdown(c["key"])
        assert md.startswith(f"# {doc} 하나 — `{c['key']}`") and "- 전제" not in md and "## 단계마다 조건" in md and "원본 문서" not in md.split("## 시작 점검")[0]   # 물려받을 전제 파일이 없다 — 그 줄을 적지 않는다
        mine = next(x for x in workflow.listing()["tasks"] if x["job"] == c["key"])
        assert mine["custom"] and mine["premiseFrom"] == job and mine["flow"] == [] and [(r["role"], r["kind"], [u["stage"] for u in r["unit"]]) for r in mine["roles"]] == [("target", kind, ["g1", "g2"])]
    # 한 줄 설명 — 놓은 줄에서
    desc = lambda *units: workflow.custom_desc({"shape": "single", "source": "", "target": "plan", "flow": _one(*units)})  # noqa: E731
    assert desc("values") == "사업계획서 하나의 프로젝트 구성을 정합니다 — 정한 차례대로 진행합니다." and desc("heads", "tables") == "사업계획서 하나의 헤딩 · 템플릿을 뽑고 표의 칸 역할을 라벨로 붙입니다 — 정한 차례대로 진행합니다."
    assert desc("apply", "adjust", "tablesLlm") == "사업계획서 하나의 절 · 표 행 · 표 열을 프로젝트 구성에 맞추고 헤딩 · 템플릿을 뽑아 서식을 템플릿에 맞추고 표의 칸 역할을 라벨로 붙입니다 — 정한 차례대로 진행합니다."
    assert desc("hand") == "사업계획서 하나에 놓은 줄을 정한 차례대로 진행합니다."
    # 전제 — 적은 글이 있으면 그 글 · 비웠으면 그 종류의 붙박이의 것(이관의 전제가 아니다): 그 파일이 생기면 물려받고 맨 앞에 차례 한 줄
    c = C.all()[0]
    assert job_prompts.get(c["key"]) is None
    jobs = C.path().parent / "jobs"
    jobs.mkdir(exist_ok=True)
    (jobs / "plan_to_report.md").write_text("# 이관\n\n계획서의 내용을 보고서로 옮긴다\n", encoding="utf-8")
    monkeypatch.setenv("NFM_JOBS", str(jobs))
    assert job_prompts.get(c["key"]) is None and job_prompts.get("plan_to_report")   # 이관의 전제가 있어도 물려받지 않는다
    (jobs / "plan_fit.md").write_text("# 표준화\n\n내용은 쓰지 않는다\n", encoding="utf-8")
    got = job_prompts.get(c["key"])
    assert got["job"] == c["key"] and job_prompts.body(got["text"]) == workflow.picked_line(c) + "\n\n내용은 쓰지 않는다"
    C.update(c["key"], {"premise": "표만 본다"})
    assert job_prompts.get(c["key"])["text"] == "표만 본다" and "- 전제: 조립할 때 적은 글" in workflow.task_markdown(c["key"])


def test_only_composed_single_workflows_are_served_when_the_custom_switch_is_on(on, monkeypatch):
    """서버가 맡는 조건 — 조립한 것에만 연 틀(OPEN_CUSTOM)을 켜면 조립한 문서 하나만 서버가 맡고 붙박이 양식 표준화 · 양식 맞추기는 그대로 화면이 돈다 · 끄면 조립한 것도 아니다."""
    c = _make("plan")
    mine, std, fit, relay, gather = (S.definition(k) for k in (c["key"], "plan_fit", "report_fit", "plan_to_report", "plan_merge"))
    served = lambda t: [S.served(t, g["id"]) for g in t["stages"]]  # noqa: E731
    before = {t["job"]: served(t) for t in (relay, gather)}
    monkeypatch.setattr(S, "OPEN_CUSTOM", set())   # 꺼 보면 — 조립한 것도 화면이 돈다
    assert served(mine) == [False, False, False] and not any(served(std)) and not any(served(fit)) and S.need(mine) == []
    monkeypatch.setattr(S, "OPEN_CUSTOM", {"single"})
    assert served(mine) == [True, True, True] and S.need(mine) == ["target"]
    assert not any(served(std)) and not any(served(fit)) and S.need(std) == S.need(fit) == []   # 붙박이는 그대로(조립한 것만 서버로)
    assert {t["job"]: served(t) for t in (relay, gather)} == before and "single" not in S.OPEN
    # 서버가 못 돌리는 줄이 있는 묶음 · 문서 칸이 그 틀이 아닌 정의는 맡지 않는다(나머지 조건은 같다)
    odd = {**mine, "roles": (*mine["roles"], {"role": "source", "name": "사업계획서", "kind": "plan", "many": False, "title": "원본 문서"})}
    assert not any(served(odd)) and not any(served({**mine, "custom": False}))
    # 화면에 내는 상태 — 묶음마다 서버가 맡고 줄의 on 은 빈 글 · 문서 칸은 목적 하나
    v = S.view(mine, {"target": {"id": "d1", "name": "문서.hwpx", "format": "hwpx"}, "source": None}, {"d1": None})
    assert [(g["id"], g["no"], g["server"]) for g in v["stages"]] == [("g1", "1단계", True), ("g2", "2단계", True), ("g3", "3단계", True)] and v["sig"] == C.sig(c) and v["ready"]
    assert v["docs"] == {"target": {"id": "d1", "name": "문서.hwpx", "format": "hwpx"}, "source": None} and all(s["on"] == "" for g in v["stages"] for s in g["steps"])
    assert [s["key"] for s in v["stages"][0]["steps"]] == ["open", "read", "load", "values", "review", "plan", "apply"]
    monkeypatch.setattr(S, "OPEN_CUSTOM", set())
    assert served(mine) == [False, False, False]


def test_api_offers_the_single_lines_and_saves_the_definition(on, client):
    """고를 줄 API(GET /api/tasks?v=2 의 byShape.single) · 검사 · 만들기 · 고치기 · 지우기 — 화면이 읽는 꼴."""
    v = client.get("/api/tasks?v=2").json()
    box, gather = v["byShape"]["single"], v["byShape"]["gather"]
    assert set(box) == {"units", "homes", "flow", "flows", "pairs", "names", "baseNames"}   # baseNames = 문서 종류마다의 기본 이름(도구 이름 고치기 — spec_워크플로우 ② §18-19)
    units = {u["key"]: u for u in box["units"]}
    assert [u["key"] for u in box["units"]] == list(C.SINGLE_UNITS) and "open" not in units
    cols = set(next(u for u in gather["units"] if u["place"] == "doc"))   # 취합형과 같은 칸
    assert all(set(u) - {"col"} == cols for u in box["units"]) and all(("col" in u) == (u["place"] == "flow") and u.get("col", "target") == "target" for u in box["units"])
    assert all(u["roles"] == ["target"] and u["each"] is False and u["server"] is True for u in box["units"])   # 칸이 하나다 — 모든 줄이 그 칸에
    assert all(u["family"] == ("common" if k == "hand" else "single") for k, u in units.items()) and units["hand"]["home"] == "hand" and units["hand"]["kind"] == "hand"
    assert all((u["place"], u["kind"], u["change"], u["paid"], u["optional"], tuple(u["needs"]), tuple(u["gives"])) ==
               (U.SINGLE[k]["place"], U.SINGLE[k]["kind"], U.SINGLE[k]["change"], U.SINGLE[k]["paid"], U.SINGLE[k]["optional"], U.SINGLE[k]["needs"], U.SINGLE[k]["gives"]) for k, u in units.items() if k != "hand")
    assert units["apply"]["uses"] == [{"unit": "values", "must": False}] and units["adjust"]["uses"] == [{"unit": "headsLlm", "must": False}] and units["values"]["name"] == "프로젝트 구성 추출"
    assert box["homes"] == [{"id": "single_config", "name": "1단계 프로젝트 구성"}, {"id": "single_heads", "name": "2단계 헤딩 추출"}, {"id": "single_tables", "name": "3단계 표"}, {"id": "hand", "name": "사람이 하는 일"}]
    assert {u["home"] for u in box["units"]} == {h["id"] for h in box["homes"]} and (units["apply"]["home"], units["adjust"]["home"], units["tableTools"]["home"]) == ("single_config", "single_heads", "single_tables")
    # 처음 줄 목록 — 그 문서 종류의 붙박이(사업계획서 = 양식 표준화 · 연차보고서 = 양식 맞추기)의 묶음 · 줄에서 준비를 뺀 것
    for kind, job in C.SINGLE_BASE.items():
        want = [(g["name"], [s["key"] for s in g["steps"] if s["key"] != "open"]) for g in workflow.BY_JOB[job]["stages"]]
        assert _names(box["flows"][kind]) == [x for x in want if x[1]] and all(s == {"unit": s["unit"], "on": []} for g in box["flows"][kind] for s in g["steps"]), kind
    assert box["flow"] == box["flows"]["plan"] and _names(box["flows"]["plan"]) == PLAN and _names(box["flows"]["report"]) == REPORT and set(box["flows"]) == {"plan", "report"}
    assert box["pairs"] == [{"value": ">plan", "source": "", "target": "plan", "name": "사업계획서"}, {"value": ">report", "source": "", "target": "report", "name": "연차보고서"}]
    assert box["names"]["report"]["apply"] == "반영" and box["names"]["plan"]["apply"] == "적용(문서에 반영)" and set(box["names"]["plan"]) == set(box["names"]["report"]) == set(C.SINGLE_UNITS)
    assert next(s for s in v["shapes"] if s["id"] == "single")["soon"] == "" and v["pairs"] == [{"source": "plan", "target": "report", "name": "사업계획서 → 연차보고서"}]   # 이관형의 것은 그대로
    # 검사 — 문서 짝을 안 보내면 그 틀의 첫 짝(원본 없음 → 사업계획서) · 목적 종류만 보내도 된다
    for body, kind in (({"shape": "single", "flow": box["flow"]}, "plan"), ({"shape": "single", "source": "", "target": "report", "flow": box["flows"]["report"]}, "report")):
        got = client.post("/api/tasks/check", json=body).json()
        assert got["errors"] == [] and got["std"] is False and got["sig"] == C.sig({"shape": "single", "source": "", "target": kind, "flow": got["flow"]}), got
    assert client.post("/api/tasks/check", json={"shape": "single", "flow": _one("config")}).json() == {"errors": ["놓을 수 없는 줄입니다 — config"], "warns": [], "flow": [{"id": "g1", "name": "a", "steps": [{"unit": "config", "on": []}]}],
                                                                                                    "std": False, "sig": None}
    for shape in ("single", "gather"):   # 줄 목록 없이 배정(이관의 표준 차례로 채우기)을 보내도 그 틀에서는 「줄이 없음」 으로 답한다(이관의 표준 차례를 지으려다 넘어지지 않는다)
        got = client.post("/api/tasks/check", json={"shape": shape, "assign": {"source": [], "target": ["stage_review"]}})
        assert got.status_code == 200 and got.json()["errors"] == ["묶음을 하나 이상 두세요"], (shape, got.text)
    odd = client.post("/api/tasks/check", json={"shape": "single", "target": ["x"], "flow": _one("heads")})   # 꼴이 틀린 문서 종류 — 넘어지지 않고 문서 짝의 거절
    assert odd.status_code == 200 and odd.json()["errors"] == ["문서 하나 워크플로우의 목적 문서는 사업계획서 · 연차보고서 가운데 하나입니다(원본 문서는 없습니다)"]
    # 만들기 · 목록 · 고치기 · 지우기
    r = client.post("/api/tasks", json={"name": "보고서 구조 맞추기", "shape": "single", "source": "", "target": "report", "flow": box["flows"]["report"]})
    assert r.status_code == 201, r.text
    t = r.json()["task"]
    key = t["key"]
    assert (t["shape"], t["v"], t["source"], t["target"], t["sourceName"], t["targetName"], t["groups"], t.get("assign")) == ("single", 2, "", "report", "", "연차보고서", ["g1", "g2"], None)
    assert t["sig"] == C.sig(C.get(key)) and t["descAuto"] == "연차보고서 하나의 절 · 표 행 · 표 열을 프로젝트 구성에 맞춥니다 — 정한 차례대로 진행합니다." and set(t["does"]) == {"g1", "g2"}
    assert (t["inUse"], t["listed"], t["editWhy"], t["deleteWhy"]) == (0, 0, None, None) and _names(t["flow"]) == REPORT
    assert client.post("/api/tasks", json={"name": "옛 꼴 하나", "shape": "single", "source": "", "target": "plan", "assign": {"source": [], "target": ["stage_review"]}}).status_code == 400   # 문서 하나는 줄 목록으로만
    assert client.post("/api/tasks", json={"name": "거꾸로", "shape": "single", "flow": _one("apply", "values")}).json()["detail"] == "「적용(문서에 반영)」 은 「프로젝트 구성 추출」 뒤에 와야 합니다"
    assert [x["key"] for x in client.get("/api/tasks?v=2").json()["tasks"]] == [key] and client.get("/api/tasks").json()["tasks"] == [] and client.get("/api/tasks").json()["hidden"] == 1   # 판 없이 읽는 옛 탭에는 안 실린다
    js = client.get("/api/tasks.js?v=2").text
    assert f'"{key}"' in js and '"shape": "single"' in js and '"source": ""' in js and key not in client.get("/api/tasks.js").text
    assert server._job_ok(key) and not server._gather_job(key)
    mine = next(x for x in client.get("/api/workflow").json()["tasks"] if x["job"] == key)
    assert mine["custom"] and mine["name"] == "보고서 구조 맞추기" and [r_["role"] for r_ in mine["roles"]] == ["target"] and [s["key"] for s in mine["stages"][0]["steps"]] == ["open", "values", "review"]
    assert all(s["on"] == "" and s["onText"] == "" for g in mine["stages"] for s in g["steps"])
    u = client.put(f"/api/tasks/{key}", json={"flow": [{"name": "구성과 구조", "steps": _L("values", "apply")}]}).json()["task"]
    assert u["groups"] == ["g1"] and u["sig"] != t["sig"] and u["shape"] == "single" and client.put(f"/api/tasks/{key}", json={"target": "plan"}).status_code == 400
    check = client.post("/api/tasks/check", json={"key": key, "flow": _one("values", "apply")}).json()   # 고치는 정의 — 틀 · 문서 짝을 그것에서
    assert check["errors"] == [] and check["warns"] == ["문서를 바꾸는 줄: 반영"]
    assert client.delete(f"/api/tasks/{key}").json() == {"deleted": True} and client.get("/api/tasks?v=2").json()["tasks"] == []


# ---------------------------------------------------------------- 진짜 서버 — 조립한 문서 하나의 작업: 문서 칸 · 상태 · 실행(붙박이 양식 맞추기는 그대로 화면에서)
@pytest.fixture
def live(monkeypatch):
    from app import merge_api
    server.DOCS.clear()
    merge_api._CACHE.clear()
    monkeypatch.setattr(C, "SINGLE_OPEN", True)
    monkeypatch.setattr(S, "OPEN_CUSTOM", {"single"})   # 통합 때의 값 — OPEN 은 그대로 둔다(붙박이 문서 하나는 닫힌 채)
    monkeypatch.setitem(X.WAIT, "poll", 0.05)
    for k, v in (("settle", 0.2), ("poll", 0.02)):
        monkeypatch.setitem(X.FENCE_WAIT, k, v)
    for d in (X.RUNS, X.BUSY, X.LAST, X.FENCE, X.NOTICE, X.REPORTS):
        d.clear()
    X.configure(unit_steps)
    yield TestClient(server.app)
    for d in (X.RUNS, X.BUSY, X.LAST, X.FENCE, X.NOTICE, X.REPORTS):
        d.clear()


def _wait(c, wid, n, seconds=240):
    t0 = time.time()
    while c.get(f"/api/works/{wid}/flow/live").json()["run"] and time.time() - t0 < seconds:
        time.sleep(0.1)
    return c.get(f"/api/works/{wid}/flow/runs/{n}").json()


def _upload(c, job, project, kind="report"):
    doc = c.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    r = c.put(f"/api/works/{doc}/task", json={"kind": "rnd", "file": kind, "job": job, "project": project})
    assert r.status_code == 200, r.text
    return doc


def test_a_composed_single_document_is_its_own_target_and_runs_on_the_server(live):
    """조립한 문서 하나의 작업 — 그 문서가 곧 목적 문서(짝 문서를 찾지 않는다 · 붙박이 문서 하나와 같은 꼴) · 그 정의의 묶음을 서버 실행기가 돈다(확정 전이면 멈춘다 — 저절로 확정하지 않는다) ·
    붙박이 「연차보고서 양식 맞추기」 는 그대로 화면에서(서버가 맡지 않는다)."""
    c = live
    r = c.post("/api/tasks", json={"name": "보고서 구조만", "shape": "single", "source": "", "target": "report", "flow": [{"name": "구성", "steps": _L("values")}, {"name": "구조", "steps": _L("plan", "apply")}]})
    assert r.status_code == 201, r.text
    key = r.json()["task"]["key"]
    doc = _upload(c, key, "조립 하나")
    mate = _upload(c, key, "조립 하나", kind="plan")   # 같은 묶음에 든 다른 종류의 문서 — 원본으로 읽지 않는다(문서마다 제 문서 칸)
    pair, old = unit_steps.pair(doc), unit_steps.pair(_upload(c, "report_fit", "붙박이"))
    assert pair["job"] == key and pair["scope"][:2] == ["조립 하나", key] and pair["target"]["id"] == doc and pair["source"] is None and "sources" not in pair
    assert pair["kinds"] == old["kinds"] == {"target": None, "source": None} and set(pair) == set(old) and pair["file"] == "report"   # 붙박이 문서 하나와 같은 꼴
    assert unit_steps.pair(mate)["target"]["id"] == mate and unit_steps.pair(mate)["source"] is None
    assert works.TARGET_FILE.get(key) == "report" and C.source_file(key) is None
    v = c.get(f"/api/works/{doc}/flow").json()
    assert [(g["id"], g["no"], g["server"]) for g in v["stages"]] == [("g1", "1단계", True), ("g2", "2단계", True)] and v["docs"]["target"]["id"] == doc and v["docs"]["source"] is None and v["ready"]
    assert [[s["key"] for s in g["steps"]] for g in v["stages"]] == [["open", "values"], ["plan", "apply"]] and v["job"] == key and v["sig"] == C.sig(C.get(key))
    # 붙박이 양식 맞추기 — 서버가 맡지 않는다(화면에서)
    builtin = old["target"]["id"]
    w = c.get(f"/api/works/{builtin}/flow").json()
    assert all(not g["server"] and g["steps"] is None for g in w["stages"])
    refused = c.post(f"/api/works/{builtin}/flow/runs", json={"from": "config", "to": "frame"})
    assert refused.status_code == 200 and refused.json()["run"] is None and refused.json()["reason"] == "client"   # 「화면이 돈다」 는 답
    # 조립한 것의 실행 — 확정 전이면 멈춘다(문서 하나의 관문: 이관의 자동 확정이 돌지 않는다) → 확정 → 구조 반영까지
    halted = _wait(c, doc, c.post(f"/api/works/{doc}/flow/runs", json={"from": "g1", "to": "g2"}).json()["run"]["n"])
    assert halted["status"] == "halted" and halted["halt"]["code"] == "notConfirmed" and halted["job"] == key, halted
    assert c.post(f"/api/docs/{doc}/divisions/confirm", json={"values": M.SMALL_VALUES}).status_code == 200
    rec = _wait(c, doc, c.post(f"/api/works/{doc}/flow/runs", json={"from": "g1", "to": "g2"}).json()["run"]["n"])
    assert rec["status"] == "done" and rec["steps"][-1]["key"] == "apply" and U.fit_done(unit_steps.div_facts(doc)), rec
    assert [g["left"] for g in c.get(f"/api/works/{doc}/flow").json()["stages"]] == [0, 0]
    # 워크플로우를 바꿀 때 — 문서 하나로 조립한 것은 그 목적 종류로(붙박이 양식 맞추기 · 표준화와 같다) · 쓰는 중인 정의는 줄을 못 바꾸고 못 지운다
    plan = c.post("/api/tasks", json={"name": "계획서 헤딩만", "shape": "single", "source": "", "target": "plan", "flow": _one("heads")}).json()["task"]["key"]
    moved = c.post(f"/api/works/{builtin}/workflows/activate", json={"job": plan})
    assert moved.status_code == 200 and (moved.json()["task"]["job"], moved.json()["task"]["file"]) == (plan, "plan"), moved.text
    assert c.put(f"/api/tasks/{key}", json={"flow": _one("values")}).status_code == 409 and c.delete(f"/api/tasks/{key}").status_code == 409
