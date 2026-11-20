"""실행 단위 · 서버 쪽 상태 셈(spec_워크플로우 ② §18-2 「실행 단위」 · ② §17-4 「파일 · 의존 규칙」 — app/workflow_units.py · app/workflow_state.py):
단위가 등록부의 단계 줄과 맞는지 · 선언이 닫혀 있는지 · 의존 규칙(AST) · 「문서 검토」 줄의 상태가 화면의 식과 같은지."""
import ast
from pathlib import Path

from app import workflow
from app import workflow_state as S
from app import workflow_units as U

APP = Path(workflow.__file__).parent


def _imports(name):
    """그 파일이 가져오는 앱 코드(함수 안의 것도) — `app.x` 꼴의 이름들."""
    tree, out = ast.parse((APP / f"{name}.py").read_text(encoding="utf-8")), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names if a.name.split(".")[0] == "app"}
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "app":
            out |= {f"app.{a.name}" for a in node.names} if node.module == "app" else {node.module}
    return out


def test_import_boundaries():
    """단위 표는 다른 앱 코드를 가져오지 않고, 상태 셈은 정의와 단위만 가져온다 — 서버 쪽 이름을 아는 파일은 문(unit_steps) 하나."""
    assert _imports("workflow_units") == set()
    assert _imports("workflow_state") <= {"app.workflow", "app.workflow_units", "app.custom_tasks"}
    for name in ("workflow_exec", "workflow_exec_api"):
        if (APP / f"{name}.py").is_file():
            assert _imports(name) <= {"app.workflow", "app.workflow_units", "app.workflow_state", "app.custom_tasks", "app.workflow_exec"}, name


def test_units_are_well_formed_and_closed():
    givers = {f for fam in U.FAMILIES.values() for u in fam.values() for f in u["gives"]}
    for fam, units in U.FAMILIES.items():
        for key, u in units.items():
            where = f"{fam}.{key}"
            assert u["key"] == key and u["place"] in U.PLACES and u["kind"] in U.KINDS, where
            assert u["change"] in workflow.CHANGE and u["paid"] in ("", "doc", "stage"), where
            assert set(u["roles"]) <= set(U.ROLES) and (bool(u["roles"]) == (u["place"] == "doc")), where   # 문서마다의 줄만 역할을 고른다
            assert set(u["needs"]) | set(u["gives"]) | set(u["spoils"]) | set(u["redo"]) <= set(U.FACTS), where
            assert set(u["needs"]) <= givers and set(u["spoils"]) <= givers and set(u["redo"]) <= givers, where   # 먼저 있어야 할 것 · 무르는 것마다 그것을 주는 단위가 있다
            assert not u["via"] or U.unit(u["via"], fam) is not None, where
            assert u["change"] != "doc" or "source" not in u["roles"], where   # 문서를 바꾸는 줄은 원본 문서에 놓을 수 없다(원본은 바뀌지 않는다)
            assert not u["paid"] or u["kind"] == "auto", where
    assert not set(U.RELAY) & set(U.COMMON) and not set(U.GATHER) & set(U.COMMON)   # 한 워크플로우 안에서 key 는 하나


def test_every_registry_step_of_the_relay_has_a_unit_that_agrees():
    """붙박이 이관 · 일반 단계 넷의 준비 중이 아닌 모든 단계 줄에 단위가 있고, 문서 바뀜 · 선택 · 하는 문서 · 유료가 등록부의 줄과 같다."""
    task = workflow.task_of("plan_to_report")
    steps = [(g["id"], s) for g in task["stages"] for s in g["steps"] if not s["soon"]]
    steps += [(mid, s) for mid, _, make, _ in workflow.STAGE_MODULES for s in make(*workflow._GENERIC) if not s["soon"]]
    assert steps
    for gid, s in steps:
        u, where = U.unit(s["key"], "relay"), f"{gid}.{s['key']}"
        assert u is not None, where
        assert u["change"] == s["change"] and u["optional"] == s["optional"], where
        if s["on"] in ("source", "target", "both"):
            assert u["place"] == "doc" and set(U.roles_of(s["on"])) <= set(u["roles"]), where
        elif s["on"]:
            assert u["place"] == s["on"], where   # pair · flow
        assert not u["paid"] or "llm" in s["by"], where   # 유료 단위의 줄은 누가에 LLM 이 있다
        assert u["home"] in ("", gid) or gid in ("review", "frame", "map", "clean"), where
    keys = {s["key"] for _, s in steps}
    assert {k for k, u in {**U.COMMON, **U.RELAY}.items() if u["kind"] != "hand"} == keys   # 남는 단위도 없다(사람이 하는 일은 등록부의 줄이 아니다)


def _facts(doc, got, llm=False, job=None):
    return {"id": doc, "heads": {"s2": got, "s3": got, "llm": llm, "job": job}}


def _docs(a, b=None):
    return [{"role": "source", "title": "사업계획서", "facts": a}] + ([{"role": "target", "title": "연차보고서", "facts": b}] if b is not None else [])


def test_review_lines_follow_the_screen_rules():
    """헤딩 · 표 분석 = 문서마다 헤딩 그래프 · 표 구조가 있으면 끝 / LLM 검증·보완 = 거침 | LLM 을 못 씀 | 건너뜀(뒤 둘은 「건너뜀」) · 도는 중이면 끝이 아님 · 유료 대상 = 안 거쳤고 안 건너뛴 문서."""
    base = {"ready": True, "lack": [], "llm": True, "skip": []}
    assert U.state("heads", {**base, "docs": _docs(_facts("a", True), _facts("b", True))})["st"] == "done"
    got = U.state("heads", {**base, "docs": _docs(_facts("a", True), _facts("b", False, job={"status": "running", "chain": None}))})
    assert got["st"] == "busy" and "연차보고서 없음" in got["text"] and "분석 중" in got["text"]
    got = U.state("heads", {**base, "docs": _docs(_facts("a", True), _facts("b", False, job={"status": "failed", "error": "까닭"}))})
    assert got["st"] == "failed" and "분석 실패 — 까닭" in got["text"]
    assert U.state("heads", {**base, "ready": False, "docs": []})["st"] == "todo"
    assert U.state("heads", {**base, "docs": _docs(None)})["st"] == "blocked"

    one = lambda f, **more: U.state("headsLlm", {**base, **more, "docs": _docs(f)})  # noqa: E731
    assert one(_facts("a", False))["st"] == "todo" and one(_facts("a", False))["paid"] == ["a"]   # 분석이 아직 없어도 유료 대상으로 센다(실행이 분석한 뒤 부른다)
    todo = one(_facts("a", True))
    assert todo["st"] == "todo" and todo["paid"] == ["a"] and "유료" in todo["text"]
    did = one(_facts("a", True, llm=True))
    assert did["st"] == "done" and not did["skipped"] and did["paid"] == []
    off = one(_facts("a", True), llm=False)
    assert off["st"] == "done" and off["skipped"] and off["paid"] == [] and "건너뜁니다" in off["text"]
    skip = one(_facts("a", True), skip=["a"])
    assert skip["st"] == "done" and skip["skipped"] and skip["paid"] == []
    run = one(_facts("a", True, llm=True, job={"status": "running", "chain": "llm"}))
    assert run["st"] == "busy"   # 거친 결과가 있어도 도는 동안은 끝이 아니다
    both = U.state("headsLlm", {**base, "skip": ["b"], "docs": _docs(_facts("a", True, llm=True), _facts("b", True))})
    assert both["st"] == "done" and not both["skipped"] and [p["skipped"] for p in both["per"]] == [False, True]
    assert U.state("link", base) is None   # 서버가 아직 세지 않는 줄


PAIR = {"target": {"id": "b", "name": "보고서.hwpx", "format": "hwpx"}, "source": {"id": "a", "name": "계획서.hwpx", "format": "hwpx"}}


def test_view_of_the_built_in_relay():
    task = S.definition("plan_to_report")
    assert S.family(task) == "relay" and S.need(task) == ["source", "target"]
    assert [(g["id"], S.served(task, g["id"])) for g in task["stages"]] == [("review", True), ("frame", False), ("map", False), ("clean", False)]
    v = S.view(task, PAIR, {"a": _facts("a", True), "b": _facts("b", False)}, llm=True)
    assert v["ready"] and v["job"] == "plan_to_report" and v["sig"] == S.sig(task) and v["docs"]["target"]["id"] == "b"
    review, frame = v["stages"][0], v["stages"][1]
    assert [(s["key"], s["st"]) for s in review["steps"]] == [("files", "done"), ("heads", "now"), ("headsLlm", "todo")]
    assert (review["done"], review["total"], review["left"], review["can"], review["paid"]) == (0, 2, 2, True, ["a"])
    assert frame["server"] is False and frame["steps"] is None and frame["can"] is False   # 아직 화면이 세는 묶음 — 서버는 지어내지 않는다
    done = S.view(task, PAIR, {"a": _facts("a", True, llm=True), "b": _facts("b", True)}, llm=True)["stages"][0]
    assert (done["done"], done["total"], done["can"], done["why"]) == (2, 2, False, "남은 단계가 없습니다")
    live = S.view(task, PAIR, {"a": _facts("a", True), "b": _facts("b", True)}, llm=True, running={"stage": "review", "key": "headsLlm"})["stages"][0]
    assert [s["st"] for s in live["steps"]] == ["done", "done", "run"]


def test_view_without_a_document_slot_is_not_ready():
    task = S.definition("plan_to_report")
    v = S.view(task, {**PAIR, "source": None}, {}, llm=True)
    assert not v["ready"] and "사업계획서" in v["why"]
    review = v["stages"][0]
    assert review["can"] is False and review["why"] == v["why"] and review["steps"][0]["st"] == "now"
    docx = S.view(task, {**PAIR, "target": {**PAIR["target"], "format": "docx"}}, {}, llm=True)
    assert not docx["ready"] and "hwpx" in docx["why"]


def test_signature_changes_only_with_the_lines():
    task = S.definition("plan_to_report")
    assert len(S.sig(task)) == 10 and S.sig(task) == S.sig(workflow.task_of("plan_to_report"))
    assert S.sig(S.definition("plan_merge")) != S.sig(task)
    assert S.definition("") is None and S.definition("nope") is None
