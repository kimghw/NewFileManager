"""문서 하나(가족 single — 양식 표준화 plan_fit · 양식 맞추기 report_fit)를 서버 실행기로(spec_워크플로우 ② §18-13 「걸음 6 — 문서 하나」 — app/workflow_units.py SINGLE · app/workflow_exec.py 의 그 절):
가짜 문으로 실행의 규칙(확정 관문 · 구조 반영 · 이미 맞음과 못 맞춤 · 같은 검사 · 지원하지 않는 양식 · 구성 읽기)을, 진짜 서버로 끝점의 새 가지(구조가 이미 맞을 때의 반영 기록)를 본다."""
import time

import pytest
from fastapi.testclient import TestClient

import merge_data as M
from app import unit_steps
from app import workflow_exec as X
from app import workflow_state as S
from app import workflow_units as U
from test_workflow_exec import V2, FitFake, _done, fit  # noqa: F401 — fit = 이관 쌍의 가짜 문(그 시험 파일의 fixture)


class OneFake(FitFake):
    """문서 하나(t)뿐인 워크플로우의 가짜 문 — 원본이 없다."""

    def __init__(self, job="report_fit"):
        super().__init__()
        self.job_key, self.source = job, None
        self.divs["t"].update(input=V2)
        self.std_init()

    def pair(self, wid):
        if wid != "t":
            return None
        return {"job": self.job_key, "scope": ["시험", self.job_key, 1], "file": "report", "kinds": {"target": None, "source": None}, "target": {"id": "t", "name": "문서.hwpx", "format": "hwpx"}, "source": None}

    # ---- 분석 상태(헤딩 · 템플릿 · 서식 · 표 — GET …/analysis 의 꼴)와 그 배경 일(양식 표준화의 2 · 3단계)
    h, t_, hl, tl = "done", "done", "none", "none"   # 헤딩 그래프 · 표 구조(스크립트) · 그 LLM 판정의 상태
    undecided, place, sure, adjust_codes, tl_fail = 0, 0, 0, (), False

    def std_init(self):
        self.tpls, self.effects, self.on_llm, self.spawn = {}, {}, {"T1": 3}, {}   # 템플릿 id → {state, at, change} · LLM 이어 돌리기가 계획을 받는 템플릿 · 반영 뒤 새로 생기는 템플릿
        return self

    def analysis(self, doc, fresh=True):
        if not hasattr(self, "tpls"):
            self.std_init()
        rows = [{"tpl": k, "no": i + 1, **x} for i, (k, x) in enumerate(self.tpls.items())]
        planned = [x for x in rows if x["state"] == "planned"]
        llm = lambda st: {"state": st, "text": {"done": "LLM 판정함", "none": "LLM 판정 안 함"}.get(st, st), "error": "까닭" if st == "failed" else None}  # noqa: E731
        job = self.jobs.get(doc) or {}
        return {"rev": self.rev[doc], "busy": job.get("status") == "running", "llmPlan": [{"key": "heads", "run": self.hl != "done"}],
                "items": [{"key": "heads", "name": "헤딩", "state": self.h, "short": "헤딩 120", "llm": llm(self.hl), "undecided": self.undecided},
                          {"key": "templates", "hints": [{"sure": True}] * self.sure},
                          {"key": "formats", "place": self.place, "noRep": 0, "apply": {"state": "", "text": ""},
                           "llm": {"state": "none", "text": "", "planned": len(planned), "change": sum(x.get("change", 0) for x in planned), "moved": 0, "reps": 0, "list": rows, "left": None, "kept": 0, "unanswered": 0, "omitted": 0}},
                          {"key": "tables", "name": "표", "state": self.t_, "short": "표 30", "llm": llm(self.tl)}]}

    def _go(self, doc, kind, effect):
        got = self._begin(doc, kind)
        if got.ok:
            self.effects[doc] = effect
        return got

    def job(self, doc):
        was = (self.jobs.get(doc) or {}).get("status")
        got = super().job(doc)
        j = self.jobs.get(doc) or {}
        if was == "running" and j.get("status") != "running":
            fn = getattr(self, "effects", {}).pop(doc, None)
            if fn and j.get("status") == "done" and not j.get("stopped"):
                fn()
        return got

    def start_heads(self, doc, how="first"):
        self.calls.append(("how", doc, how))
        def done():
            self.h = "done" if how != 3 else self.h
            self.t_ = "done"
        return self._go(doc, "heads", done)

    def start_llm(self, doc, skill=None):
        def done():   # 헤딩 · 템플릿 → 표 → 서식 정리 계획
            self.hl = self.tl = "done"
            for k, n in self.on_llm.items():
                self.tpls[k] = {"state": "planned", "at": 1, "change": n}
        return self._go(doc, "llm", done)

    def start_formats(self, doc, skill=None):
        self.calls.append(("formats", doc))
        def done():
            for k, x in self.tpls.items():
                if x["state"] in ("none", "stale"):
                    self.tpls[k] = {"state": "planned", "at": 2, "change": 2}
        return self._go(doc, "llm", done)

    def start_tables_llm(self, doc):
        self.calls.append(("tablesLlm", doc))
        return self._go(doc, "heads", lambda: setattr(self, "tl", "failed" if self.tl_fail else "done"))

    def adjust_apply(self, doc, rev, plans=None):
        self.calls.append(("adjust", doc, rev, dict(plans or {})))
        self.seen.append(("adjust", X.fence_why(doc), doc in X.FENCE))
        codes = list(self.adjust_codes)
        if codes:
            self.adjust_codes = codes[1:]
            if codes[0] != "ok":
                return unit_steps.Outcome(codes[0], "표준 검사에 걸렸습니다" if codes[0] == "rejected" else "그 사이에 문서가 바뀌었습니다")
        done = [k for k, x in self.tpls.items() if x["state"] == "planned" and k in (plans or {})]
        for k in done:
            self.tpls[k] = {"state": "applied"}
        self.place = self.sure = 0
        self.rev[doc] += 1
        self.tpls.update(self.spawn)
        self.spawn = {}
        return unit_steps.Outcome("ok", "", {"templates": [{"tpl": k, "levels": [], "splits": []} for k in done], "changed": ["a", "b", "c"], "placed": [], "left": [], "merged": []})


@pytest.fixture
def one(monkeypatch):
    f = OneFake()
    monkeypatch.setattr(X, "UNIT", f)
    monkeypatch.setattr(S, "OPEN", {"relay", "single"})   # 문서 하나의 틀을 연 것으로(화면이 따라오는 갈래 「라」 에서 실제로 연다)
    monkeypatch.setitem(X.WAIT, "poll", 0.005)
    for k, v in (("settle", 0.3), ("limit", 0.8), ("poll", 0.01)):
        monkeypatch.setitem(X.FENCE_WAIT, k, v)
    for d in (X.RUNS, X.BUSY, X.LAST, X.FENCE, X.NOTICE, X.REPORTS):
        d.clear()
    yield f
    _done("t", 5)
    for d in (X.RUNS, X.BUSY, X.LAST, X.FENCE, X.NOTICE, X.REPORTS):
        d.clear()


def test_the_single_family_is_closed_until_the_screens_follow(monkeypatch):
    """문서 하나의 틀은 화면이 따라올 때까지 닫혀 있다(OPEN) — 열면 양식 맞추기의 묶음 셋 · 양식 표준화의 1단계를 서버가 맡는다. 단위가 없는 문서 하나 워크플로우(일반 편집 · 서식 복사)는 가족이 없다."""
    fit_, std = S.definition("report_fit"), S.definition("plan_fit")
    assert S.family(fit_) == S.family(std) == "single" and S.family(S.definition("doc_edit")) == S.family(S.definition("style_copy")) == "" and S.family(S.definition("plan_merge")) == "gather"
    assert S.base(fit_) == "target" and S.base(S.definition("plan_to_report")) == "source" and S.base(S.definition("plan_merge")) == "target"
    assert not any(S.served(fit_, g["id"]) for g in fit_["stages"]) and not S.served(std, "config")
    monkeypatch.setattr(S, "OPEN", {"relay", "single"})
    assert all(S.served(fit_, g["id"]) for g in fit_["stages"]) and S.served(std, "config") and S.need(fit_) == ["target"]
    for job in ("doc_edit", "style_copy", "plan_merge"):
        assert not any(S.served(S.definition(job), g["id"]) for g in S.definition(job)["stages"]), job
    # 줄 key 가 겹쳐도 가족의 단위 · 상태 식 · 처리 함수가 먼저다 — 문서 하나의 plan · apply 는 이관의 넣기 단위가 아니다
    assert U.unit("apply", "single") is U.SINGLE["apply"] and U.unit("apply", "relay") is U.RELAY["apply"] and U.unit("apply", "") is None and U.unit("guide", "single") is U.COMMON["guide"]
    relay = S.definition("plan_to_report")
    assert X._handler(fit_, {"unit": U.unit("apply", "single"), "key": "apply"}) is X._do_one_apply and X._handler(relay, {"unit": U.unit("apply", "relay"), "key": "apply"}) is X._do_apply
    assert not X._fill_need(fit_) and X._fill_need(relay)   # 문서 하나에는 연결 목록을 읽지 않는다


def test_every_registry_step_of_the_single_workflows_has_a_unit_that_agrees(monkeypatch):
    """서버가 맡는 문서 하나 묶음의 모든 단계 줄에 그 가족의 단위가 있고, 문서 바뀜 · 선택이 등록부의 줄과 같다(사람이 고르는 줄에는 처리 함수가 없고, 실행기가 하는 줄에는 있다)."""
    monkeypatch.setattr(S, "OPEN", {"relay", "single"})
    seen = set()
    for job in ("report_fit", "plan_fit"):
        task = S.definition(job)
        for g in task["stages"]:
            if not S.served(task, g["id"]):
                continue
            for s in g["steps"]:
                u, where = U.unit(s["key"], "single"), f"{job}.{g['id']}.{s['key']}"
                assert u is not None and u["server"] and U.SINGLE.get(s["key"]) is u, where
                assert u["change"] == s["change"] and u["optional"] == s["optional"] and s["on"] == "", where
                assert (u["kind"] == "auto") == (s["key"] in X.FAMILY_HANDLERS["single"]), where
                assert not u["paid"] or "llm" in s["by"], where
                seen.add(s["key"])
    assert seen == set(U.SINGLE)   # 남는 단위도 없다


def test_one_document_halts_until_a_person_confirms_then_fits_the_structure(one):
    """확정 전이면 멈춘다(저절로 확정하지 않는다) → 사람이 확정한 뒤: 울타리 안에서 계획 → 같은 검사 → 반영 한 번 · 끝 글은 화면 실행의 글."""
    v = X.status_of("t")
    assert [g["id"] for g in v["stages"]] == ["open", "config", "frame"] and all(g["server"] for g in v["stages"]) and v["docs"]["source"] is None and v["ready"]
    config, frame = v["stages"][1], v["stages"][2]
    assert [(s["key"], s["st"]) for s in config["steps"]] == [("values", "now"), ("review", "todo")] and config["can"] and config["left"] == 1
    assert frame["can"] is False and frame["why"] == "「프로젝트 구성」 이 먼저입니다" and frame["after"] == ["config"] and frame["change"] is True
    X.start("t", {"from": "config", "to": "frame"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "notConfirmed" and rec["halt"]["key"] == "values" and "확인한 뒤 프로젝트 「시험」에 저장(확정)하세요" in rec["end"]["text"]
    assert not [c for c in one.calls if c[0] in ("confirm", "plan", "apply")]   # 확정도 계획도 반영도 하지 않았다
    X.start("t", {"from": "frame"})   # 묶음 하나로 눌러도 — 확정이 먼저(그 묶음의 줄이 요구하는 것을 주는 앞 묶음)
    rec = _done("t")
    assert rec["status"] == "left" and "「프로젝트 구성」 이 덜 끝났습니다" in rec["end"]["text"] and not [c for c in one.calls if c[0] == "plan"]
    one.config_confirm("t", V2)   # 사람이 확정
    one.calls.clear()
    v = X.status_of("t")
    assert v["stages"][1]["left"] == 0 and v["stages"][2]["can"] and [(s["key"], s["st"]) for s in v["stages"][2]["steps"]] == [("plan", "now"), ("apply", "todo")]
    X.start("t", {"from": "config", "to": "frame", "skip": ["k1"]})
    rec = _done("t")
    assert rec["status"] == "done", rec["end"]
    assert [c for c in one.calls if c[0] in ("plan", "apply")] == [("plan", "t", ("k1",)), ("apply", "t", "p1", 0)]
    assert one.seen[0][:3] == ("plan", "", True) and one.seen[1] == ("other", X.FENCE_TEXT) and not X.FENCE and not X.NOTICE   # 울타리 안에서 — 사람 편집은 409
    assert [s["key"] for s in rec["steps"]] == ["apply"] and rec["end"]["text"] == "끝남 — 반영 완료 · 편집 차례 1"   # 남은 것이 없던 앞 묶음(프로젝트 구성)은 글을 더하지 않는다
    frame = X.status_of("t")["stages"][2]
    assert frame["left"] == 0 and [(s["key"], s["done"], s["text"]) for s in frame["steps"]] == [("plan", True, ""), ("apply", True, "문서 구조를 프로젝트 구성에 맞췄습니다")]
    with pytest.raises(X.Refuse) as e:
        X.start("t", {"from": "frame"})
    assert e.value.reason == "noWork"
    one.divs["t"]["input"] = {**V2, "current": 2}   # 당해 차년도만 다름 — 끝남 그대로(화면 divConfirmKey)
    assert X.status_of("t")["stages"][2]["left"] == 0
    one.divs["t"]["partial"] = [{"values": {**V2, "stages": [3]}, "only": "g1"}]   # 그 뒤 다른 값으로 한 자리만 반영 — 끝남이 아니다
    assert X.status_of("t")["stages"][2]["left"] == 2


@pytest.mark.parametrize("case", ["already", "cannot", "issues", "orgs", "rejected"])
def test_one_document_tells_already_fit_from_cannot_fit_and_halts_on_the_same_check(one, case):
    one.config_confirm("t", V2)
    if case in ("already", "cannot"):
        one.apply_code, one.already = "nothing", case == "already"
    elif case == "rejected":
        one.apply_code = "rejected"
    else:
        one.stops, one.stops_kind = ("미해결 2곳", "issues") if case == "issues" else ("기관 「B」 의 차례가 마지막 반영과 다릅니다(공동 1 → 공동 2)", "orgs")
    X.start("t", {"from": "frame"})
    rec = _done("t")
    if case == "already":   # 구조가 이미 값에 맞음 — 그 확인을 반영 기록으로 남기고 끝(화면의 「같은 계획」 은 서버에 없다)
        assert rec["status"] == "done" and rec["end"]["text"] == "끝남 — 현재 구성과 맞습니다 — 바꿀 자리가 없습니다 · 지원 안 됨 1곳은 그대로"
        line = X.status_of("t")["stages"][2]["steps"][1]
        assert line["done"] and line["text"] == "이미 프로젝트 구성에 맞습니다" and one.divs["t"]["applied"]["adopted"]
    elif case == "cannot":   # 못 맞춤 — 「이미 맞음」 과 같은 글로 끝내지 않는다
        assert rec["status"] == "halted" and rec["halt"]["code"] == "same" and rec["end"]["text"] == "멈춤 — 맞출 수 있는 자리가 없습니다 · 지원 안 됨 1곳" and one.divs["t"]["applied"] is None
    elif case == "rejected":
        assert rec["status"] == "halted" and rec["halt"]["code"] == "rejected" and len([c for c in one.calls if c[0] == "plan"]) == 1
    else:
        tail = "쓴 내용이 다른 기관 이름 아래에 남을 수 있습니다. " if case == "orgs" else ""
        assert rec["status"] == "halted" and rec["halt"]["code"] == "stops" and rec["end"]["text"] == f"멈춤 — {one.stops} — {tail}목록에서 확인한 뒤 「② 반영」 을 누르세요"
        assert not [c for c in one.calls if c[0] == "apply"]
    assert not X.FENCE and not X.NOTICE


def test_an_unsupported_form_skips_the_structure_lines(one):
    """구조 반영을 지원하지 않는 양식 — 확정 · 계획 · 반영 줄은 「건너뜀」 으로 끝난 것(헤딩 · 표 묶음을 막지 않는다) · 할 일이 없다."""
    one.divs["t"]["supported"] = False
    v = X.status_of("t")
    assert [g["left"] for g in v["stages"]] == [0, 0, 0] and all(s["skipped"] for s in v["stages"][2]["steps"]) and v["stages"][1]["steps"][0]["skipped"]
    assert "지원하지 않습니다" in v["stages"][2]["steps"][1]["text"]
    with pytest.raises(X.Refuse) as e:
        X.start("t", {"from": "config", "to": "frame"})
    assert e.value.reason == "noWork" and not one.calls


def test_plan_fit_reads_the_values_into_the_input_but_never_confirms(one):
    """양식 표준화 1단계 — 입력 값이 없으면 문서에 적힌 값을 입력으로 채우고(확정하지 않는다) 확정 줄에서 멈춘다 · 읽을 값이 없으면 남기고 멈춘다(값을 지어내지 않는다)."""
    one.job_key = "plan_fit"
    one.divs["t"]["input"] = None
    v = X.status_of("t")["stages"]
    assert [g["id"] for g in v] == ["config", "heads", "tables"] and v[0]["server"] and [s["key"] for s in v[0]["steps"]] == ["open", "read", "load", "values", "review", "plan", "apply"]
    assert (v[0]["total"], v[0]["done"], v[0]["left"]) == (4, 1, 3) and v[0]["steps"][0]["done"]   # 준비는 끝난 것 · 선택 줄(읽기 · 불러오기 · 자리 확인)은 세지 않는다
    X.start("t", {"from": "config"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["key"] == "values" and [(s["key"], s["status"]) for s in rec["steps"]] == [("read", "done")]
    assert one.divs["t"]["input"] == V2 and ("save", "t") in one.calls and ("confirm", "t") not in one.calls
    assert rec["steps"][0]["text"] == "사업계획서에서 읽은 값을 입력 칸에 채웠습니다(1단계 · 전체 2년 · 기관 2곳) — 확정은 따로 합니다"
    one.divs["t"]["input"], one.readv = None, None
    one.calls.clear()
    X.start("t", {"from": "config"})
    rec = _done("t")
    assert rec["status"] == "halted" and [(s["key"], s["status"]) for s in rec["steps"]] == [("read", "left")] and "값을 지어내지 않습니다" in rec["left"][0]["what"] and ("save", "t") not in one.calls
    assert "「프로젝트 구성 확정」 이 먼저입니다 — 프로젝트 구성(단계·차년도·기관)이 없습니다 — 사업계획서에서 추출" in rec["end"]["text"]


def test_relay_fit_does_not_adopt_a_structure_on_its_own(fit):  # noqa: F811
    """이관의 「프로젝트 구성 반영」 은 전과 같다 — 바꿀 것이 없는 계획을 「이미 맞음」 으로 기록하지 않는다(그 기록은 아직 닫힌 틀인 문서 하나만 켠다: 조건을 다듬은 뒤에 넓힌다 — spec_워크플로우 ④).
    반영 기록이 없으면 「반영되지 않았습니다」 로 멈춘다(이번 변경 전의 동작)."""
    fit.apply_code = "nothing"
    X.start("t", {"from": "frame"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "notApplied" and fit.divs["t"]["applied"] is None
    assert [c for c in fit.calls if c[0] == "apply"] == [("apply", "t", "p1", 0)]


# ---------------------------------------------------------------- 상태 식(화면 doc_agent_work.js agwFitStatus · agwFitApplied · app.js divSameText 의 식 그대로)
def _ctx(div, ready=True):
    return {"ready": ready, "lack": [], "llm": True, "skip": set(), "base": "target",
            "pair": {"target": {"role": "target", "title": "사업계획서", "id": "t", "facts": {"id": "t", "heads": {"s2": True, "s3": True, "llm": False, "job": None}, "div": div}}}}


def _div(inp=V2, **more):
    return {"input": inp, "applied": None, "confirmed": None, "partial": [], "form": "연구개발계획서", "supported": True, "rev": 3, "read": None, "sharing": None, "plan": None, "stale": False, **more}


def test_single_state_lines_follow_the_screen_rules():
    cf = {"values": V2, "at": 1}
    st = lambda key, div, **k: U.state(key, _ctx(div, **k), "single")  # noqa: E731
    assert st("open", _div())["st"] == "done" and st("open", _div(), ready=False)["st"] == "todo"
    assert st("read", _div())["st"] == "done" and st("read", _div(None))["st"] == "todo" and "1단계 · 전체 2년 · 기관 2곳" in st("read", _div(None, read=V2))["text"]
    assert st("values", _div())["text"] == "1단계 · 전체 2년 · 기관 2곳 — 확인한 뒤 이 문서에 저장(확정)하세요" and st("values", _div(confirmed=cf))["st"] == "done"
    assert st("values", _div(None))["text"].startswith("프로젝트 구성(단계·차년도·기관)이 없습니다 — 사업계획서에서 추출")   # 구성의 기준 = 이 문서
    assert st("values", _div({**V2, "current": 3}, confirmed=cf))["st"] == "done" and "확정한 뒤 값이 바뀌었습니다" in st("values", _div({**V2, "stages": [3]}, confirmed=cf))["text"]
    assert st("apply", _div(confirmed=cf)) == {"st": "todo", "text": ""} and st("apply", _div(applied={"values": V2, "rev": 4}))["st"] == "todo"   # 확정이 먼저
    assert st("apply", _div(confirmed=cf, applied={"values": V2, "rev": 4})) == {"st": "done", "text": "문서 구조를 프로젝트 구성에 맞췄습니다"}
    assert st("apply", _div(confirmed=cf, applied={"values": V2, "rev": 4, "adopted": True}))["text"] == "이미 프로젝트 구성에 맞습니다"
    assert st("apply", _div(confirmed=cf, applied={"values": {**V2, "stages": [3]}, "rev": 4}))["st"] == "todo"
    assert st("apply", None)["st"] == "blocked"
    plan = lambda **s: {"planId": "p", "baseRev": 3, "only": None, "skip": [], "summary": {"groups": 2, "changes": 1, "applied": 4, "added": 3, "removed": 1, "deleted": 2, **s}}  # noqa: E731
    assert st("plan", _div(confirmed=cf)) == {"st": "todo", "text": ""}
    assert st("plan", _div(confirmed=cf, plan=plan(unresolved=2))) == {"st": "done", "text": "맞출 자리 4곳 · 항목 추가 3 · 지움 1 · 글 바꿈 1 · 지워지는 글 문단 2 · 미해결 2곳"}
    assert st("plan", _div(confirmed=cf, plan=plan(), stale=True))["text"] == "계획이 낡았습니다 — 다시 계획해야 합니다"
    assert st("plan", _div(confirmed=cf, plan={**plan(), "only": "g1"}))["st"] == "todo"   # 표 하나만의 계획은 문서 전체 계획이 아니다
    assert st("plan", _div(plan=plan()))["st"] == "todo"   # 확정 전
    assert st("plan", _div(confirmed=cf, plan=plan(groups=0, changes=0, already=5)))["text"] == "현재 구성과 맞습니다 — 바꿀 자리가 없습니다"
    assert st("plan", _div(confirmed=cf, applied={"values": V2, "rev": 4}))["st"] == "done"
    assert U.state("load", _ctx(_div()), "single") is None and U.state("review", _ctx(_div()), "single") is None   # 사람이 고르는 선택 줄 — 서버가 세지 않는다
    assert U.plan_same({"unresolved": 1, "unsupported": 2}) == (False, "바꿀 수 있는 자리가 없습니다 · 미해결 1곳 · 지원 안 됨 2곳은 그대로") and U.plan_same({}) == (False, "맞출 자리를 찾지 못했습니다")
    assert U.fit_done(_div(applied={"values": {**V2, "current": 2}})) and not U.fit_done(_div(applied={"values": V2}, partial=[{"values": {**V2, "stages": [3]}}])) and not U.fit_done(_div(None, applied={"values": V2}))


# ---------------------------------------------------------------- 진짜 서버 — 양식 맞추기 하나를 끝까지 · 구조가 이미 맞을 때의 반영 기록
@pytest.fixture
def client(monkeypatch):
    from app import merge_api, server
    server.DOCS.clear()
    merge_api._CACHE.clear()
    monkeypatch.setattr(S, "OPEN", {"relay", "single"})
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


def test_report_fit_runs_on_the_real_server_and_records_a_structure_that_already_matches(client):
    from app import server
    r = client.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())})
    doc = r.json()["docId"]
    assert client.put(f"/api/works/{doc}/task", json={"kind": "rnd", "file": "report", "job": "report_fit", "project": "시험 과제"}).status_code == 200
    pair = unit_steps.pair(doc)
    assert pair["target"]["id"] == doc and pair["source"] is None and pair["job"] == "report_fit"
    v = client.get(f"/api/works/{doc}/flow").json()
    assert [g["id"] for g in v["stages"]] == ["open", "config", "frame"] and all(g["server"] for g in v["stages"]) and v["stages"][1]["steps"][0]["key"] == "values"
    halted = _wait(client, doc, client.post(f"/api/works/{doc}/flow/runs", json={"from": "config", "to": "frame"}).json()["run"]["n"])
    assert halted["status"] == "halted" and halted["halt"]["code"] == "notConfirmed"   # 확정 전 — 저절로 확정하지 않는다
    assert client.post(f"/api/docs/{doc}/divisions/confirm", json={"values": M.SMALL_VALUES}).status_code == 200
    d = unit_steps.div_facts(doc)
    assert d["plan"] is None and d["stale"] is False and d["supported"]
    rev0 = unit_steps.facts(doc)["rev"]
    rec = _wait(client, doc, client.post(f"/api/works/{doc}/flow/runs", json={"from": "config", "to": "frame"}).json()["run"]["n"])
    assert rec["status"] == "done", rec
    d = unit_steps.div_facts(doc)
    assert d["applied"] and U.fit_done(d) and rec["steps"][-1]["key"] == "apply"
    changed = unit_steps.facts(doc)["rev"] > rev0
    assert rec["end"]["text"].startswith("끝남 — " + ("반영 완료 · 편집 차례 " if changed else "현재 구성과 맞습니다"))
    assert client.get(f"/api/works/{doc}/flow").json()["stages"][2]["left"] == 0
    assert client.post(f"/api/works/{doc}/flow/runs", json={"from": "frame"}).json()["reason"] == "noWork"
    # 구조가 이미 값에 맞는데 반영 기록이 없는 문서(구조를 맞춘 문서를 새로 올린 것과 같다) — 문의 adopt 가 그 확인을 기록으로 남긴다 · 화면의 반영(adopt 없음)은 전처럼 기록하지 않는다
    s = server.DOCS[doc]
    with s.lock:
        s.division["applied"] = None
    values = unit_steps.div_facts(doc)["input"]
    plan = unit_steps.division_plan(doc, values).data
    if not (plan["summary"].get("groups") or plan["summary"].get("changes")):   # 지금 구조에 바꿀 것이 없다(자리표시를 다시 본떠도 같음)
        plain = client.post(f"/api/docs/{doc}/divisions/apply", json={"planId": plan["planId"], "expectRev": plan["baseRev"]}).json()
        assert plain["nothing"] and plain["adopted"] is False and unit_steps.div_facts(doc)["applied"] is None
        plan = unit_steps.division_plan(doc, values).data
        got = unit_steps.division_apply(doc, plan["planId"], plan["baseRev"], adopt=True)
        assert got.code == "nothing" and got.data["adopted"] is True
        d = unit_steps.div_facts(doc)
        assert d["applied"]["adopted"] is True and d["applied"]["values"] == values and U.fit_done(d)
        assert client.get(f"/api/works/{doc}/flow").json()["stages"][2]["steps"][1]["text"] == "이미 프로젝트 구성에 맞습니다"


# ================================================================ 갈래 「나」 — 양식 표준화의 2단계 「헤딩 추출」 · 3단계 「표」(화면 heads_run_all.js 「전체 실행」 · doc_agent_work.js agwStdSteps 의 식)
@pytest.fixture
def std(one):
    one.job_key = "plan_fit"
    one.divs["t"].update(confirmed={"values": V2, "at": 1}, applied={"values": V2, "rev": 0})   # 1단계는 끝난 문서
    return one


def _stage(v, gid):
    return next(g for g in v["stages"] if g["id"] == gid)


def test_heads_and_tables_stages_do_not_wait_for_the_project_structure(std):
    """양식 표준화의 헤딩 · 표 묶음은 프로젝트 구성이 남아도 돈다(헤딩 · 표 분석은 프로젝트 구성에 기대지 않는다) — 「이어서 한 번에」 만 안 끝난 묶음에서 멈춘다."""
    std.divs["t"].update(confirmed=None, applied=None)
    v = X.status_of("t")
    heads, tables = _stage(v, "heads"), _stage(v, "tables")
    assert all(g["server"] for g in v["stages"]) and _stage(v, "config")["left"] == 3 and heads["after"] == [] and heads["can"] and tables["after"] == [] and tables["can"]
    assert [(s["key"], s["st"]) for s in heads["steps"]] == [("heads", "done"), ("headsLlm", "now"), ("adjust", "todo"), ("tree", "todo")] and (heads["total"], heads["left"]) == (3, 2)
    assert heads["paid"] == ["t"] and heads["change"] is True and tables["paid"] == ["t"] and [s["key"] for s in tables["steps"]] == ["tables", "tablesLlm", "tableTools"]
    X.start("t", {"from": "tables"})   # 1단계가 남아도 묶음 하나로는 돈다
    rec = _done("t")
    assert rec["status"] == "done" and ("tablesLlm", "t") in std.calls and std.tl == "done"
    std.tl = "none"
    X.start("t", {"from": "config", "to": "tables"})   # 이어서 한 번에 — 1단계의 확정 줄에서 멈춘다(뒤 묶음을 시작하지 않는다)
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["key"] == "values" and std.calls.count(("tablesLlm", "t")) == 1


def test_heads_stage_runs_the_llm_chain_then_applies_the_plans_inside_the_fence(std):
    """헤딩 LLM 판정 · 서식 계획(이어 돌리기 — 표 판정도 같이) → 조정 「모두 반영」(울타리 안에서 다시 읽은 그 계획만) · 끝나면 3단계도 남은 것이 없다."""
    X.start("t", {"from": "heads"})
    rec = _done("t")
    assert rec["status"] == "done", rec["end"]
    assert [c for c in std.calls if c[0] in ("llm", "formats", "adjust")] == [("llm", "t"), ("adjust", "t", 0, {"T1": 1})]
    assert std.seen[-1] == ("adjust", "", True) and not X.FENCE and not X.NOTICE   # 울타리 안에서
    assert [(s["key"], s["status"]) for s in rec["steps"]] == [("heads", "nothing"), ("headsLlm", "done"), ("adjust", "done")]
    assert rec["end"]["text"] == "끝남 — 헤딩 LLM 판정 · 서식 계획 — LLM 판정함 · 조정 — 템플릿 1개 반영(맞춘 줄 3) · 「실행 취소」 한 번으로 되돌립니다"
    v = X.status_of("t")
    assert _stage(v, "heads")["left"] == 0 and _stage(v, "tables")["left"] == 0 and _stage(v, "heads")["steps"][2]["text"] == "반영할 것이 남지 않았습니다"
    with pytest.raises(X.Refuse) as e:
        X.start("t", {"from": "heads", "to": "tables"})
    assert e.value.reason == "noWork"


def test_llm_lines_are_left_not_skipped_when_the_llm_is_off(std):
    """LLM 을 쓸 수 없으면 헤딩 · 표의 LLM 줄은 「건너뜀」 이 아니라 남김(이관의 「문서 검토」 와 다르다 — 화면과 같게) · 조정도 헤딩 판정 뒤의 일이라 남는다."""
    std.ok = False
    v = X.status_of("t")
    assert _stage(v, "heads")["paid"] == [] and "LLM 을 쓸 수 없어 지금은 할 수 없습니다" in _stage(v, "heads")["steps"][1]["text"] and not _stage(v, "heads")["steps"][1]["skipped"]
    X.start("t", {"from": "heads", "to": "tables"})
    rec = _done("t")
    assert rec["status"] == "left" and rec["end"]["ok"] and not [c for c in std.calls if c[0] in ("llm", "formats", "adjust", "tablesLlm")]
    assert [x["key"] for x in rec["left"]] == ["headsLlm", "adjust", ""] and "LLM 을 쓸 수 없습니다" in rec["left"][0]["what"] and "헤딩 LLM 판정이 먼저입니다" in rec["left"][1]["what"]
    assert rec["left"][2]["what"] == "2단계 「헤딩 추출」 이 덜 끝났습니다" and _stage(X.status_of("t"), "heads")["left"] == 2   # 이어서 한 번에 — 안 끝난 묶음에서 멈춘다


def test_adjust_leaves_the_plans_when_the_heading_judgement_is_undecided(std):
    std.hl, std.tl, std.undecided = "done", "done", 2
    std.tpls["T1"] = {"state": "planned", "at": 1, "change": 4}
    X.start("t", {"from": "heads"})
    rec = _done("t")
    assert rec["status"] == "left" and not [c for c in std.calls if c[0] == "adjust"]
    assert "헤딩 판정에 미판정 2곳이 있어 반영하지 않습니다" in rec["end"]["text"] and "받은 계획은 남아 있습니다" in rec["end"]["text"]


@pytest.mark.parametrize("by", ["human", "agent", "approved"])
def test_adjust_fetches_missing_plans_only_when_the_paid_call_is_approved(std, by):
    """조정이 서식 정리 계획을 다시 받는 것은 유료 — 사람이 누른 실행 · 에이전트 카드가 승인한 문서일 때만. 승인 밖이면 받지 않고 받아 둔 것만 반영하고 남긴다."""
    std.hl = std.tl = "done"
    std.tpls.update({"T1": {"state": "planned", "at": 1, "change": 4}, "T2": {"state": "none"}})
    assert _stage(X.status_of("t"), "heads")["paid"] == []   # 반영할 것이 먼저 — 받을 계획은 그 뒤(상태 글은 반영할 것)
    X.start("t", {"from": "heads", **({"by": "agent", "paid": ["t"] if by == "approved" else []} if by != "human" else {})})
    rec = _done("t")
    if by == "agent":
        assert rec["status"] == "left" and ("formats", "t") not in std.calls and [c[3] for c in std.calls if c[0] == "adjust"] == [{"T1": 1}]
        assert "서식 정리 계획을 받지 않은 템플릿 1개(실행 카드에서 승인한 유료 호출이 아님" in rec["end"]["text"] and "조정 — 템플릿 1개 반영" in rec["end"]["text"]
    else:
        assert rec["status"] == "done", rec["end"]
        assert [c for c in std.calls if c[0] in ("formats", "adjust")] == [("formats", "t"), ("adjust", "t", 0, {"T1": 1, "T2": 2})]


def test_adjust_repeats_for_templates_born_from_the_apply_and_stops_at_the_cap(std):
    """반영으로 새로 생긴 서식 종속 템플릿에 받을 계획이 남으면 「계획 → 반영」 을 되풀이한다 · 그 사이 바뀌었으면(409) 다시 읽고 · 표준 검사가 되돌리면(422) 멈춘다."""
    std.hl = std.tl = "done"
    std.tpls["T1"] = {"state": "planned", "at": 1, "change": 4}
    std.spawn, std.adjust_codes = {"T1L2a": {"state": "none"}}, ("stale", "ok")
    X.start("t", {"from": "heads"})
    rec = _done("t")
    assert rec["status"] == "done", rec["end"]
    assert [c[:2] for c in std.calls if c[0] in ("formats", "adjust")] == [("adjust", "t"), ("adjust", "t"), ("formats", "t"), ("adjust", "t")]
    assert "조정 — 템플릿 2개 반영(맞춘 줄 6) · 「실행 취소」 2번으로 되돌립니다" in rec["end"]["text"]
    std.tpls["T3"], std.adjust_codes = {"state": "planned", "at": 5, "change": 1}, ("rejected",)
    X.start("t", {"from": "heads"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "rejected" and "표준 검사에 걸려 되돌렸습니다" in rec["end"]["text"] and not X.FENCE
    std.adjust_codes = ("stale",) * 9   # 늘 그 사이 바뀜 — 한도에서 남긴다(끝없이 돌지 않는다)
    X.start("t", {"from": "heads"})
    rec = _done("t")
    assert rec["status"] == "left" and "되풀이 한도(3번)에 닿아 멈췄습니다" in rec["end"]["text"] and len([c for c in std.calls if c[0] == "adjust"]) == 3 + 1 + 3   # 첫 실행 3번 · 되돌린 실행 1번 · 이번 실행은 한도 3번까지만


def test_tables_stage_extracts_by_script_then_judges_with_the_llm(std):
    std.t_ = "none"
    X.start("t", {"from": "tables"})
    rec = _done("t")
    assert rec["status"] == "done" and [c for c in std.calls if c[0] in ("how", "tablesLlm")] == [("how", "t", 3), ("tablesLlm", "t")]
    assert [(s["key"], s["status"]) for s in rec["steps"]] == [("tables", "done"), ("tablesLlm", "done")]
    std.tl, std.tl_fail = "none", True   # LLM 이 답을 못 냄 — 스크립트 결과로 남긴다(멈추지 않는다)
    X.start("t", {"from": "tables"})
    rec = _done("t")
    assert rec["status"] == "left" and "표 판정(LLM)이 답을 내지 못했습니다" in rec["end"]["text"] and "스크립트 결과로 남깁니다" in rec["end"]["text"]
    std.h = std.t_ = "none"   # 헤딩 그래프도 없으면 첫 분석(헤딩 그래프 → 표 구조)
    std.tl_fail, std.tl = False, "done"
    std.calls.clear()
    X.start("t", {"from": "tables"})
    rec = _done("t")
    assert rec["status"] == "done" and [c for c in std.calls if c[0] == "how"] == [("how", "t", "first")]


def test_std_helpers_port_the_screen_counts():
    """남은 것의 셈(화면 hraLeft) — 「맞출 줄 0 · 대표 변경 1」 인 계획도 반영할 것 · 줄 수가 0 이면 반영할 것이 아니다 · 확실한 종속 · 자리 맞춤은 계획이 없어도 반영할 것."""
    f = OneFake("plan_fit")
    f.tpls["T1"] = {"state": "planned", "at": 7, "change": 0}
    P = U.std_left(f.analysis("t"))
    assert P["plans"] == 1 and P["apply"] is False and P["at"] == {"T1": 7} and P["need"] == []
    v = f.analysis("t")
    next(i for i in v["items"] if i["key"] == "formats")["llm"]["reps"] = 1
    assert U.std_left(v)["apply"] is True and U.std_apply_text(U.std_left(v)) == "받아 둔 서식 정리 계획 1개(템플릿) · 대표를 바꿀 레벨 1"
    f.tpls, f.sure, f.place = {"T2": {"state": "stale"}}, 1, 5
    P = U.std_left(f.analysis("t"))
    assert P["apply"] is True and [x["tpl"] for x in P["need"]] == ["T2"] and (P["sure"], P["place"], P["plans"]) == (1, 5, 0)
    assert U.std_unseen({**P, "undecided": 2, "hints": 1, "kept": 3, "done": {"kept": 1, "unanswered": 0, "marked": 2}, "norep": 1}) == [
        "헤딩 판정의 미판정 2곳(LLM 구간 검증 실패 — 「단계별 실행」 의 헤딩 판정을 다시)", "종속 제안 1개(애매한 것 — 결과 화면의 「템플릿 관계」 절에서 고릅니다)",
        "받아 둔 계획이 남긴 것 — 에이전트가 그대로 둔 줄 3(조정 층의 칸을 눌러 계획 보기 · 「템플릿 관계」 에서 손으로)",
        "반영한 계획이 남긴 것 — 그대로 둔 줄 1 · 형광펜·필드 표지가 있어 모양만 맞춘 줄 2(글은 그대로)(「반영한 계획 보기」 · 「템플릿 관계」 에서 손으로)",
        "대표가 없는 레벨 1개(「템플릿 관계」 에서 줄 하나를 대표로 — 대표가 없으면 맞춘 레벨로 세지 않습니다)"]


def test_heads_and_tables_doors_on_the_real_server(client, monkeypatch):
    """진짜 서버 — 분석 상태의 문 · 2단계 묶음을 LLM 없이 돌리면 스크립트 줄만 하고 LLM 줄 · 조정은 남긴다 · 조정의 문은 「할 일 없음」 과 「그 사이 바뀜」 을 가른다."""
    monkeypatch.setattr(unit_steps, "llm_ok", lambda: False)   # 유료 호출을 걸지 않는다(실행기는 문의 이 값으로 LLM 줄을 남긴다)
    r = client.post("/api/docs?new=1", files={"file": (M.PLAN_FORM.name, M.PLAN_FORM.read_bytes())})
    doc = r.json()["docId"]
    assert client.put(f"/api/works/{doc}/task", json={"kind": "rnd", "file": "plan", "job": "plan_fit", "project": "시험 과제"}).status_code == 200
    v0 = unit_steps.analysis(doc)
    assert {i["key"] for i in v0["items"]} >= {"heads", "templates", "formats", "tables"} and unit_steps.analysis(doc, fresh=False) is v0 and unit_steps.analysis("nope") is None
    v = client.get(f"/api/works/{doc}/flow").json()
    assert [g["id"] for g in v["stages"]] == ["config", "heads", "tables"] and all(g["server"] for g in v["stages"]) and v["stages"][1]["after"] == [] and v["stages"][1]["paid"] == []
    rec = _wait(client, doc, client.post(f"/api/works/{doc}/flow/runs", json={"from": "heads", "to": "tables"}).json()["run"]["n"])
    assert rec["status"] == "left", rec
    assert [(s["key"], s["status"]) for s in rec["steps"]][:3] == [("heads", "done"), ("headsLlm", "left"), ("adjust", "left")]
    now = unit_steps.analysis(doc)
    assert {i["key"]: i["state"] for i in now["items"] if i["key"] in ("heads", "tables")} == {"heads": "done", "tables": "done"}
    got = unit_steps.adjust_apply(doc, now["rev"] + 99)   # 화면이 본 문서 차례가 지금 것이 아니다 — 그 사이 바뀜(할 일 없음이 아니다)
    assert got.code == "stale" and unit_steps.start_formats("nope").code == "missing" and unit_steps.start_tables_llm("nope").code == "missing"
