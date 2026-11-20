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
    assert [(g["id"], S.served(task, g["id"])) for g in task["stages"]] == [("review", True), ("frame", True), ("map", False), ("clean", False)]
    v = S.view(task, PAIR, {"a": _facts("a", True), "b": _facts("b", False)}, llm=True)
    assert v["ready"] and v["job"] == "plan_to_report" and v["sig"] == S.sig(task) and v["docs"]["target"]["id"] == "b"
    review, frame = v["stages"][0], v["stages"][1]
    assert [(s["key"], s["st"]) for s in review["steps"]] == [("files", "done"), ("heads", "now"), ("headsLlm", "todo")]
    assert (review["done"], review["total"], review["left"], review["can"], review["paid"]) == (0, 2, 2, True, ["a"])
    assert frame["server"] and [s["key"] for s in frame["steps"]] == ["configLoad", "config", "division", "reheads", "reheadsLlm"] and frame["can"] is False and frame["why"] == "1단계 「문서 검토」 이 먼저입니다"   # 걸음 2 — 서버가 센다
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


# ---------------------------------------------------------------- 걸음 2 — 「구성 맞추기」 의 상태 식(화면 app.js taskSteps 의 config · division · reheads · reheadsLlm 그대로)
V2 = {"stages": [2], "orgs": {"lead": "인텍", "joint": ["가나대"], "nonprofit": [False, False], "outside": [], "overseas": [], "entrust": []}, "subs": [], "current": 1}


def _div(inp=None, applied=None, confirmed=None, read=None, project="시험 과제"):
    return {"input": inp, "applied": applied, "confirmed": confirmed, "partial": [], "form": "연구개발계획서", "supported": True, "rev": 3, "read": read,
            "sharing": {"project": project, "shared": True} if project else None}


def _fit(sdiv, tdiv, *, theads=(True, 3, 3), tasked=False, tjob=None, llm=True, skip=(), tllm=False):
    got, r2, r3 = theads
    pair = {"source": {"role": "source", "title": "사업계획서", "id": "a", "facts": {"id": "a", "heads": {"s2": True, "s3": True, "llm": True, "job": None}, "div": sdiv}},
            "target": {"role": "target", "title": "연차보고서", "id": "b", "facts": {"id": "b", "heads": {"s2": got, "s3": got, "rev2": r2, "rev3": r3, "llm": tllm, "asked": tasked, "job": tjob}, "div": tdiv}}}
    return {"ready": True, "lack": [], "llm": llm, "skip": set(skip), "pair": pair}


def test_confirm_is_valid_without_the_current_year_like_the_screen():
    """확정 유효 = 당해 차년도를 뺀 값이 같음(화면 divConfirmValid) — 서버 confirmed.valid(settings 전체의 해시)와 뜻이 다르다."""
    cf = {"values": V2, "at": 1}
    assert U.confirm_valid({**V2, "current": 2}, cf) and not U.confirm_valid({**V2, "stages": [3]}, cf) and not U.confirm_valid(None, cf) and not U.confirm_valid(V2, None)
    assert U._config(_fit(None, _div(V2, confirmed={**cf, "valid": False})))["st"] == "done"   # 서버 valid 가 거짓이어도(당해 차년도만 다름) 끝남
    assert U._config(_fit(None, _div({**V2, "current": 2}, confirmed=cf)))["text"].startswith("프로젝트 「시험 과제」에 확정함(")
    assert "확정한 뒤 값이 바뀌었습니다" in U._config(_fit(None, _div({**V2, "stages": [3]}, confirmed=cf)))["text"]
    assert U._config(_fit(None, _div(None)))["text"].startswith("프로젝트 구성(단계·차년도·기관)이 없습니다 — 사업계획서에서 추출")
    assert U._config(_fit(None, _div(V2, project="")))["text"] == "1단계 · 전체 2년 · 기관 2곳 — 확인한 뒤 이 문서에 저장(확정)하세요"
    assert U._config(_fit(None, None))["st"] == "blocked"


def test_values_differ_like_the_screen_not_like_the_merge_pairs():
    """두 문서의 값 견줌 = 정리한 꼴 전체(화면 taskDivDiff — 단계 · 기관 이름 · 구분 · 사업기간 · 세부과제) — 당해 차년도는 안 견준다."""
    assert U.div_diff(V2, {**V2, "current": 2}) == []
    assert U.div_diff(V2, {**V2, "stages": [1, 1]}) == ["단계·차년도(2년 ↔ 1+1년)"]
    assert U.div_diff(V2, {**V2, "orgs": {**V2["orgs"], "nonprofit": [False, True]}}) == ["기관 이름·구분"]   # 비영리만 달라도(서버 values_diff 는 이름 모음만 본다)
    assert U.div_diff(V2, {**V2, "orgs": {**V2["orgs"], "joint": ["가나대", "다라연"]}}) == ["공동 기관(1곳 ↔ 2곳)"]
    assert U.div_diff(V2, {**V2, "subs": ["x"], "period": {"start": "2026-01-01", "end": "2027-12-31"}}) == ["사업기간", "세부과제"]


def test_division_line_follows_the_screen_rules():
    cf = {"values": V2, "at": 1}
    applied = {"values": V2, "rev": 5}
    assert U._division(_fit(_div(V2), _div(V2)))["st"] == "todo" and U._division(_fit(_div(V2), _div(V2)))["text"] == ""   # 확정이 먼저
    got = U._division(_fit(_div(V2), _div({**V2, "stages": [3]}, confirmed={"values": {**V2, "stages": [3]}})))
    assert got["st"] == "todo" and got["text"] == "사업계획서(1단계 · 전체 2년 · 기관 2곳)와 다름 — 단계·차년도(2년 ↔ 3년)"
    got = U._division(_fit(_div(V2), _div(V2, confirmed=cf)))
    assert got["text"] == "값은 사업계획서와 같음(1단계 · 전체 2년 · 기관 2곳) · 연차보고서에 아직 반영 전"
    got = U._division(_fit(_div(V2, applied=applied), _div({**V2, "current": 2}, confirmed=cf, applied={"values": {**V2, "current": 2}, "rev": 5})))
    assert got["st"] == "done" and got["text"] == "사업계획서와 같음 · 연차보고서에 반영됨 — 1단계 · 전체 2년 · 기관 2곳 · 당해 차년도는 연차보고서 2차년도(사업계획서 1차년도)"
    got = U._division(_fit(_div(V2), _div({**V2, "current": 2}, confirmed=cf, applied={"values": V2, "rev": 5})))   # 반영한 값이 지금 값과 다르다(당해 차년도) — 반영 전
    assert got["st"] == "todo" and "아직 반영 전" in got["text"]
    got = U._division(_fit(_div(None, read=V2), _div(V2, confirmed=cf)))   # 원본에 저장한 값이 없어 문서에서 읽음
    assert got["st"] == "todo" and got["text"].startswith("사업계획서에 저장된 값이 없어 문서에서 읽었습니다(")
    assert U._division(_fit(_div(None), _div(V2, confirmed=cf)))["text"].startswith("사업계획서(기준)에 프로젝트 구성 값이 없습니다")


def test_reheads_lines_follow_the_screen_rules():
    cf = {"values": V2, "at": 1}
    fit = lambda **k: _fit(_div(V2, applied={"values": V2, "rev": 5}), _div(V2, confirmed=cf, applied={"values": V2, "rev": 5}), **k)  # noqa: E731
    assert U._reheads(fit(theads=(True, 5, 5)))["st"] == "done" and U._reheads(fit(theads=(True, 5, 5)))["text"] == "헤딩 그래프·표 구조가 구조 반영 뒤의 것입니다"
    stale = U._reheads(fit(theads=(True, 3, 5)))
    assert stale["st"] == "todo" and "구조 반영 전 것입니다" in stale["text"] and "LLM 판정은" not in stale["text"]
    kept = U._reheads(fit(theads=(True, 3, 3), tasked=True))
    assert kept["st"] == "todo" and "LLM 판정은 다음 줄에서 다시 받습니다" in kept["text"]
    keep = U._reheads(fit(theads=(True, 3, 3), tasked=True, llm=False))   # LLM 을 쓸 수 없으면 반영 전 LLM 결과를 그대로 둔다
    assert keep["st"] == "done" and keep["keep"] and keep["text"].startswith("구조 반영 전 분석(LLM 판정을 거친 결과")
    assert U._reheads(fit(theads=(False, None, None)))["text"].endswith("분석이 없습니다 — 다시 분석(스크립트)")
    assert U._reheads(fit(theads=(True, 3, 5), tjob={"status": "running", "chain": None}))["st"] == "busy"
    # LLM — 앞 줄이 끝나야 셈하지만 유료 대상은 미리 센다(화면 taskPaidDocs)
    early = U._reheads_llm(fit(theads=(True, 3, 3)))
    assert early["st"] == "todo" and early["paid"] == ["b"] and early["text"] == ""
    assert U._reheads_llm(fit(theads=(True, 3, 3), skip=["b"]))["paid"] == [] and U._reheads_llm(fit(theads=(True, 3, 3), llm=False))["paid"] == []
    todo = U._reheads_llm(fit(theads=(True, 5, 5)))
    assert todo["st"] == "todo" and todo["paid"] == ["b"] and "유료" in todo["text"]
    did = U._reheads_llm(fit(theads=(True, 5, 5), tllm=True))
    assert did["st"] == "done" and not did["skipped"] and did["paid"] == []
    off = U._reheads_llm(fit(theads=(True, 3, 3), tasked=True, llm=False))   # keep 이고 LLM 을 못 씀 — 「건너뜀」
    assert off["st"] == "done" and off["skipped"]


def test_view_of_the_frame_stage_reads_both_documents():
    task = S.definition("plan_to_report")
    assert set(S.need(task)) == {"source", "target"} and all(U.unit(k)["server"] for k in ("configLoad", "config", "division", "reheads", "reheadsLlm"))
    cf = {"values": V2, "at": 1}
    facts = {"a": {"id": "a", "heads": {"s2": True, "s3": True, "llm": True, "job": None}, "div": _div(V2, applied={"values": V2, "rev": 5})},
             "b": {"id": "b", "heads": {"s2": True, "s3": True, "rev2": 5, "rev3": 5, "llm": True, "asked": True, "job": None}, "div": _div(V2, confirmed=cf, applied={"values": V2, "rev": 5})}}
    frame = S.view(task, PAIR, facts, llm=True)["stages"][1]
    assert [(s["key"], s["done"]) for s in frame["steps"]] == [("configLoad", False), ("config", True), ("division", True), ("reheads", True), ("reheadsLlm", True)]
    assert (frame["done"], frame["total"], frame["left"]) == (4, 4, 0) and frame["change"] is True
