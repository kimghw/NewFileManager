"""문서 하나(가족 single — 양식 표준화 plan_fit · 양식 맞추기 report_fit)를 서버 실행기로(spec_워크플로우 ② §18-13 「걸음 6 — 문서 하나」 — app/workflow_units.py SINGLE · app/workflow_exec.py 의 그 절):
가짜 문으로 실행의 규칙(확정 관문 · 구조 반영 · 이미 맞음과 못 맞춤 · 같은 검사 · 지원하지 않는 양식 · 구성 읽기)을, 진짜 서버로 끝점의 새 가지(구조가 이미 맞을 때의 반영 기록)를 본다."""
import contextlib
import copy
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

import merge_data as M
from app import unit_steps
from app import workflow_exec as X
from app import workflow_state as S
from app import workflow_units as U
from test_workflow_exec import V2, FitFake, _done, _fit_on, fit  # noqa: F401 — fit = 이관 쌍의 가짜 문(그 시험 파일의 fixture) · _fit_on = 「구성 맞추기」 줄의 하는 문서를 바꾼 정의


class OneFake(FitFake):
    """문서 하나(t)뿐인 워크플로우의 가짜 문 — 원본이 없다."""

    def __init__(self, job="report_fit"):
        super().__init__()
        self.job_key, self.source = job, None
        self.divs["t"].update(input=V2)
        self.hints, self.named, self.last_skip = [], 0, ()   # 추가한 자리(문단 id) · 구분 값에 없는 기관 이름이 적힌 자리 수 · 마지막 계획이 뺀 자리
        self.on_plan = self.on_save = self.on_analysis = None   # 그 일 직전에 끼어드는 다른 화면(시험이 건다 — 계획 · 입력 저장 · 분석 상태 읽기)
        self.std_init()

    def pair(self, wid):
        if wid != "t":
            return None
        return {"job": self.job_key, "scope": ["시험", self.job_key, 1], "file": "report", "kinds": {"target": None, "source": None}, "target": {"id": "t", "name": "문서.hwpx", "format": "hwpx"}, "source": None}

    # ---- 프로젝트 구성(진짜 문 unit_steps 의 꼴 — 입력의 판 hash · 추가한 자리 hints · 값 없는 계획 · 입력이 비어 있을 때만 저장 · 반영 기록의 범위 skip · hints)
    @staticmethod
    def _hash(values):
        return json.dumps(values, sort_keys=True, ensure_ascii=False) if values else None

    def div_facts(self, doc):
        d = super().div_facts(doc)
        if d is not None:
            d.update(hints=sorted(self.hints), hash=self._hash(d.get("input")))
        return d

    def config_save(self, doc, values, if_empty=False):
        if self.on_save:
            self.on_save()
        if if_empty and self.divs[doc]["input"]:   # 그 사이 입력이 생겼다 — 덮지 않는다
            self.calls.append(("kept", doc))
            return unit_steps.Outcome("nothing", "입력 값이 이미 있습니다", {"saved": False})
        return super().config_save(doc, values)

    def division_plan(self, doc, values, skip=(), expect=None):
        if self.on_plan:
            self.on_plan()
        now = self.divs[doc]["input"]
        if expect is not None and expect != self._hash(now):   # 입력이 그 판이 아니다 — 계획하지 않는다(값을 저장하기 전에)
            self.calls.append(("planStale", doc))
            return unit_steps.Outcome("stale", "프로젝트 구성 값이 그 사이에 바뀌었습니다")
        got = super().division_plan(doc, now if values is None else values, skip)   # 값이 없으면 저장된 입력 그대로(덮지 않는다)
        self.last_skip = tuple(skip)
        got.data["settingsHash"] = self._hash(self.divs[doc]["input"])
        return got

    def division_apply(self, doc, plan_id, expect, adopt=False):
        if self.named and self.apply_code == "nothing":   # 값이 다르다고 확인된 자리가 남음 — 끝점이 「이미 맞음」 으로 적지 않는다(기존 기록 그대로)
            self.calls.append(("apply", doc, plan_id, expect))
            return unit_steps.Outcome("nothing", "할 일이 없습니다", {"nothing": True, "adopted": False, "named": self.named, "summary": {"already": 3, "unsupported": self.named}, "rev": self.rev[doc]}, self.rev[doc])
        got = super().division_apply(doc, plan_id, expect, adopt)
        if got.code == "ok" or (got.code == "nothing" and (got.data or {}).get("adopted")):
            self.divs[doc]["applied"].update(skip=sorted(self.last_skip), hints=sorted(self.hints))   # 그 반영의 범위(진짜 끝점 server._division_scope)
        return got

    # ---- 분석 상태(헤딩 · 템플릿 · 서식 · 표 — GET …/analysis 의 꼴)와 그 배경 일(양식 표준화의 2 · 3단계)
    h, t_, hl, tl = "done", "done", "none", "none"   # 헤딩 그래프 · 표 구조(스크립트) · 그 LLM 판정의 상태
    undecided, place, sure, adjust_codes, tl_fail = 0, 0, 0, (), False
    chain_tl = "done"   # 헤딩 LLM 판정의 이어 돌리기가 같이 부른 표 판정이 남기는 상태(failed = 그 표 판정이 답을 못 냄)
    graph = None        # 헤딩 그래프의 표시 [실행 번호, 만든 때] — 분석 상태 헤딩 항목의 run · at
    keep = False        # 참 = 문의 2초 값 흉내(fresh=False 는 같은 문서 차례의 방금 읽은 값을 돌려준다 — unit_steps.analysis)
    only_plans = None   # 서식 정리 계획 받기가 이번에 받는 템플릿(없으면 받을 것 모두) · person_stop = 그 작업을 사람이 문서 진행표에서 멈춘 것 · swap = 내 작업이 끝난 자리에 선 남의 작업의 표시
    person_stop, swap = False, None

    def std_init(self):
        self.tpls, self.effects, self.on_llm, self.spawn = {}, {}, {"T1": 3}, {}   # 템플릿 id → {state, at, change} · LLM 이어 돌리기가 계획을 받는 템플릿 · 반영 뒤 새로 생기는 템플릿
        self.cache, self.ids = None, 0
        return self

    def analysis(self, doc, fresh=True):
        if not hasattr(self, "tpls"):
            self.std_init()
        if self.on_analysis:
            self.on_analysis()
        if not fresh and self.keep and self.cache is not None and self.cache["rev"] == self.rev[doc]:
            return self.cache
        rows = [{"tpl": k, "no": i + 1, **x} for i, (k, x) in enumerate(self.tpls.items())]
        planned = [x for x in rows if x["state"] == "planned"]
        llm = lambda st: {"state": st, "text": {"done": "LLM 판정함", "none": "LLM 판정 안 함"}.get(st, st), "error": "까닭" if st == "failed" else None}  # noqa: E731
        job = self.jobs.get(doc) or {}
        self.cache = {"rev": self.rev[doc], "busy": job.get("status") == "running",
                      "llmPlan": [{"key": "heads", "run": self.hl != "done"}, {"key": "tables", "run": self.hl != "done" or self.tl != "done"}],   # 헤딩을 다시 지으면 표 판정도 같이 부른다(analysis.llm_plan)
                      "items": [{"key": "heads", "name": "헤딩", "state": self.h, "short": "헤딩 120", "llm": llm(self.hl), "undecided": self.undecided,
                                 **({"run": self.graph[0], "at": self.graph[1]} if self.graph else {})},
                                {"key": "templates", "hints": [{"sure": True}] * self.sure},
                                {"key": "formats", "place": self.place, "noRep": 0, "apply": {"state": "", "text": ""},
                                 "llm": {"state": "none", "text": "", "planned": len(planned), "change": sum(x.get("change", 0) for x in planned), "moved": 0, "reps": 0, "list": rows, "left": None, "kept": 0, "unanswered": 0, "omitted": 0}},
                                {"key": "tables", "name": "표", "state": self.t_, "short": "표 30", "llm": llm(self.tl)}]}
        return self.cache

    def _begin(self, doc, kind, polls=2):
        got = super()._begin(doc, kind, polls)
        if got.ok:   # 작업마다 다른 표시(진짜 헤딩 작업의 started)
            self.ids += 1
            self.jobs[doc]["started"] = got.data["started"] = self.ids
        return got

    def _go(self, doc, kind, effect):
        got = self._begin(doc, kind)
        if got.ok:
            self.effects[doc] = effect
        return got

    def job(self, doc):
        j0 = self.jobs.get(doc) or {}
        if self.swap is not None and j0.get("status") == "running" and j0.get("started") != self.swap and self.left.get(doc, 0) <= 1:
            # 내 작업이 끝났고(그 결과는 남았다) 다음 읽기 전에 남의 작업이 그 자리에서 돌기 시작했다 — 끝나지 않는 작업
            fn = self.effects.pop(doc, None)
            if fn:
                fn()
            self.jobs[doc] = {"status": "running", "chain": "llm", "error": None, "started": self.swap}
            self.left[doc] = 10 ** 9
        was = (self.jobs.get(doc) or {}).get("status")
        got = super().job(doc)
        j = self.jobs.get(doc) or {}
        if was == "running" and j.get("status") != "running":
            fn = getattr(self, "effects", {}).pop(doc, None)
            if fn and j.get("status") == "done" and not j.get("stopped"):
                fn()
            if self.person_stop:   # 사람이 문서 진행표에서 그 작업을 멈췄다(끝난 작업의 보기에 stopping)
                j["stopping"] = True
                got = unit_steps.Outcome("ok", "", dict(j), 0)
        return got

    def start_heads(self, doc, how="first"):
        self.calls.append(("how", doc, how))
        def done():
            self.h = "done" if how != 3 else self.h
            self.t_ = "done"
        return self._go(doc, "heads", done)

    def start_llm(self, doc, skill=None):
        def done():   # 헤딩 · 템플릿 → 표 → 서식 정리 계획
            self.hl, self.tl = "done", self.chain_tl
            for k, n in self.on_llm.items():
                self.tpls[k] = {"state": "planned", "at": 1, "change": n}
        return self._go(doc, "llm", done)

    def start_formats(self, doc, skill=None):
        self.calls.append(("formats", doc))
        def done():
            for k, x in self.tpls.items():
                if x["state"] in ("none", "stale") and (self.only_plans is None or k in self.only_plans):
                    self.tpls[k] = {"state": "planned", "at": 2, "change": 2}
        return self._go(doc, "llm", done)

    def start_tables_llm(self, doc):
        self.calls.append(("tablesLlm", doc))
        return self._go(doc, "heads", lambda: setattr(self, "tl", "failed" if self.tl_fail else "done"))

    def adjust_apply(self, doc, rev, plans=None, graph=None):
        self.calls.append(("adjust", doc, rev, dict(plans or {})))
        self.graphs = [*getattr(self, "graphs", []), graph]
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
    assert [s["key"] for s in rec["steps"]] == ["apply"] and rec["end"]["text"] == "끝남 — 반영 완료 · 편집 차례 1 · 반영에서 뺀 자리 1곳은 그대로"   # 남은 것이 없던 앞 묶음(프로젝트 구성)은 글을 더하지 않는다
    frame = X.status_of("t")["stages"][2]
    assert frame["left"] == 0 and [(s["key"], s["done"], s["text"]) for s in frame["steps"]] == [("plan", True, ""), ("apply", True, "문서 구조를 프로젝트 구성에 맞췄습니다 · 반영에서 뺀 자리 1곳은 그대로")]
    with pytest.raises(X.Refuse) as e:
        X.start("t", {"from": "frame"})
    assert e.value.reason == "noWork"
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
    assert "「프로젝트 구성 추출」 이 먼저입니다 — 프로젝트 구성(단계·차년도·기관)이 없습니다 — 사업계획서에서 추출" in rec["end"]["text"]


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
    assert U.fit_done(_div(applied={"values": V2})) and not U.fit_done(_div(applied={"values": V2}, partial=[{"values": {**V2, "stages": [3]}}])) and not U.fit_done(_div(None, applied={"values": V2}))


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
    assert not (plan["summary"].get("groups") or plan["summary"].get("changes")), plan["summary"]   # 지금 구조에 바꿀 것이 없다(자리표시를 다시 본떠도 같음) — 견본이 달라져 이 전제가 깨지면 여기서 떨어진다(아래 검증을 조용히 건너뛰지 않는다)
    plain = client.post(f"/api/docs/{doc}/divisions/apply", json={"planId": plan["planId"], "expectRev": plan["baseRev"]}).json()
    assert plain["nothing"] and plain["adopted"] is False and unit_steps.div_facts(doc)["applied"] is None
    plan = unit_steps.division_plan(doc, values).data
    got = unit_steps.division_apply(doc, plan["planId"], plan["baseRev"], adopt=True)
    assert got.code == "nothing" and got.data["adopted"] is True and "named" not in got.data
    d = unit_steps.div_facts(doc)
    assert d["applied"]["adopted"] is True and d["applied"]["values"] == values and U.fit_done(d)
    assert d["applied"]["skip"] == [] and d["applied"]["hints"] == [] and d["hints"] == []   # 반영 기록에 그 계획의 범위(뺀 자리 · 추가한 자리)
    assert client.get(f"/api/works/{doc}/flow").json()["stages"][2]["steps"][1]["text"] == "이미 프로젝트 구성에 맞습니다"
    # 뺀 자리가 있는 계획(바꿀 것 없음)도 확인을 남기되 뺀 자리를 기록에 — 그 자리를 풀면(이번 실행이 빼지 않으면) 다시 계획해야 한다 · 뺀 자리를 모르는 조회는 지난 반영의 것 그대로(전에는 뺀 자리가 있으면 기록을 안 남겨 실행이 막혔다)
    key = next(c["key"] for c in plan["candidates"] if c["status"] == "already")
    with s.lock:
        s.division["applied"] = None
    plan = unit_steps.division_plan(doc, None, [key], expect=unit_steps.div_facts(doc)["hash"]).data   # 값 없이(저장된 입력으로) · 그 입력의 판일 때만
    assert plan["skip"] == [key] and plan["values"] == server.DOCS[doc].division["settings"]["values"] and not (plan["summary"].get("groups") or plan["summary"].get("changes"))
    got = unit_steps.division_apply(doc, plan["planId"], plan["baseRev"], adopt=True)
    d = unit_steps.div_facts(doc)
    assert got.data["adopted"] is True and d["applied"]["skip"] == [key]
    assert U.fit_done(d) and U.fit_done({**d, "excl": [key, "x"]}) and not U.fit_done({**d, "excl": []})
    assert client.get(f"/api/works/{doc}/flow").json()["stages"][2]["steps"][1]["text"] == "이미 프로젝트 구성에 맞습니다 · 반영에서 뺀 자리 1곳은 그대로"
    assert client.post(f"/api/works/{doc}/flow/runs", json={"from": "frame"}).json()["reason"] == "noWork"   # 뺀 자리를 알려 주지 않은 시작 — 지난 반영의 것 그대로
    rec = _wait(client, doc, client.post(f"/api/works/{doc}/flow/runs", json={"from": "frame", "skip": []}).json()["run"]["n"])   # 「뺀 자리 없음」 을 알려 준 시작 — 그 자리를 다시 본다
    d = unit_steps.div_facts(doc)
    assert rec["status"] == "done" and rec["steps"][-1]["key"] == "apply" and d["applied"]["skip"] == [] and U.fit_done({**d, "excl": []}), rec


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
    heads = _stage(X.status_of("t"), "heads")   # 받을 계획(T2)이 남았으면 실행은 그것부터 받는다(유료) — 반영할 것(T1)이 함께 있어도 유료 문서로 보인다(전에는 반영할 것이 있으면 유료 표시가 없었다: astra P2)
    assert heads["paid"] == ["t"] and heads["steps"][2]["text"] == "반영할 것 — 받아 둔 서식 정리 계획 1개(템플릿) · 대표에 맞출 줄 4 · 서식 정리 계획을 받지 않은 템플릿 1개(계획 받기 — 유료)"
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
    # 판정을 본 헤딩 그래프의 표시(분석 상태 헤딩 항목의 run · at = 문 graph_key) — 반영 직전에 지금 그래프와 견준다: 그 사이 헤딩을 다시 뽑았으면 반영하지 않는다(astra B2)
    heads = next(i for i in now["items"] if i["key"] == "heads")
    g = unit_steps.graph_key(doc)
    assert g == [heads["run"], heads["at"]] and g[0] is not None and unit_steps.graph_key("nope") is None
    got = unit_steps.adjust_apply(doc, now["rev"], {}, graph=[g[0] + 1, g[1]])
    assert got.code == "stale" and "헤딩 그래프가 그 사이에 바뀌었습니다" in got.text and unit_steps.analysis(doc)["rev"] == now["rev"]


# ================================================================ 검토 의견의 반례(artifacts/flow_single_astra_2026-11-20/answer.md — 문서 하나의 틀을 열기 전에 고친 것 · 아래 시험은 고치기 전에는 떨어졌다)
V3, V4 = {**V2, "stages": [3]}, {**V2, "stages": [4]}


def _at_fence(monkeypatch, change):
    """울타리를 기다리는 사이 다른 화면 · 같은 프로젝트의 다른 문서가 한 일 — 울타리가 올라간 직후(몸에 들어가기 전에) change() 를 한 번 부른다."""
    orig, done = X.Run.fence, []

    @contextlib.contextmanager
    def fence(self, doc):
        with orig(self, doc):
            if not done:
                done.append(1)
                change()
            yield
    monkeypatch.setattr(X.Run, "fence", fence)


# ---- 구조 반영과 확정(A1 ~ A6)
def test_other_organization_names_left_in_the_document_are_not_recorded_as_a_fit(client):
    """A1 — 값으로 바꿀 것이 없는 전체 계획이어도 **구분 값에 없는 기관 이름이 적힌 자리**(값이 다르다고 이미 확인된 자리)가 남았으면 「이미 맞음」 으로 적지 않는다: 기존 반영 기록 · 한 자리만 반영한 기록 그대로.
    이 기록은 열려 있는 틀도 쓴다(이관형의 원본 문서 · 취합의 구조 확인 — …/divisions/adopt)."""
    import gather_data as D
    from app import server
    b = D.base()["side"]   # 양식에 값(인텍 · 가나대 · 다라연)을 반영한 문서 — 기관 이름이 적혀 있다
    doc = client.post("/api/docs?new=1", files={"file": ("작성본.hwpx", b["bytes"])}).json()["docId"]
    other = copy.deepcopy(D.VALUES)
    other["orgs"]["joint"] = ["외부가", "외부나"]
    assert client.post(f"/api/docs/{doc}/divisions/confirm", json={"values": other}).status_code == 200
    plan = unit_steps.division_plan(doc, None).data
    assert unit_steps.division_apply(doc, plan["planId"], plan["baseRev"]).code == "ok"   # 값으로 바꿀 수 있는 자리를 맞춘 뒤 — 문서에는 다른 기관의 이름(가나대 · 다라연)이 남는다
    s = server.DOCS[doc]
    old = {"values": copy.deepcopy(b["values"]), "rev": 0, "at": 1.0, "planId": "old"}
    part = [{"values": copy.deepcopy(b["values"]), "only": "g", "rev": 0, "at": 1.0, "planId": "old"}]
    with s.lock:
        s.division.update(applied=copy.deepcopy(old), partial=copy.deepcopy(part), prior=[])   # 다른 값의 반영 기록이 있던 문서
    plan = unit_steps.division_plan(doc, None).data
    sm, named = plan["summary"], [c for c in plan["candidates"] if c["status"] == "unsupported" and c.get("reason") == "named"]
    assert named and sm["already"] and not (sm["groups"] or sm["changes"] or sm["unresolved"] or sm["errors"]), sm   # 「이미 맞은 자리가 있고 미해결 · 계획 오류가 없는」 바꿀 것 없는 전체 계획인데 다른 이름의 자리가 남았다
    got = unit_steps.division_apply(doc, plan["planId"], plan["baseRev"], adopt=True)
    assert got.code == "nothing" and got.data["adopted"] is False and got.data["named"] >= len(named)
    assert s.division["applied"] == old and s.division["partial"] == part   # 전에는 지금 값의 「이미 맞음」 으로 바꾸고 한 자리만 반영한 기록을 지웠다
    with s.lock:
        s.division.update(applied=None, partial=None, prior=[], plan=None)
    r = client.post(f"/api/docs/{doc}/divisions/adopt", json={}).json()   # 한 번도 반영한 적 없는 문서의 구조 확인(이관형의 원본 문서 · 취합이 계획 앞에 부른다)도 같다
    assert r["adopted"] is False and r["why"] == "named" and r["applied"] is None and s.division["applied"] is None and unit_steps.div_facts(doc)["applied"] is None


def test_a_source_document_with_other_organization_names_halts_with_that_reason(fit, monkeypatch):  # noqa: F811
    """A1 이 열려 있는 틀에 닿는 곳 — 이관형의 원본 문서 구조 확인이 「다른 이름의 기관 자리가 남음」 으로 적지 않았고 계획에도 바꿀 것이 없으면, 「반영되지 않았습니다」 가 아니라 그 까닭으로 멈춘다
    (전에는 그 문서를 「구조가 이미 값에 맞음」 으로 적고 지나갔다)."""
    _fit_on(monkeypatch, division="source", reheads="source", reheadsLlm="source")
    fit.division_adopt = lambda doc, values=None: fit.calls.append(("adopt", doc)) or unit_steps.Outcome("ok", "", {"adopted": False, "why": "named", "named": 2, "applied": None})
    fit.apply_code = "nothing"
    X.start("t", {"from": "frame"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "named" and rec["halt"]["key"] == "division" and fit.divs["s"]["applied"] is None
    assert "사업계획서에 프로젝트 구성에 없는 기관 이름이 적힌 자리가 2곳 남아 있습니다" in rec["end"]["text"]
    assert [c for c in fit.calls if c[0] in ("adopt", "plan", "apply")] == [("adopt", "s"), ("plan", "s", ()), ("apply", "s", "p1", 0)]   # 구조 확인 → 계획 → 반영(바꿀 것 없음) — 그 뒤에 멈춘다


def test_one_document_with_other_organization_names_is_not_closed_as_already_fitting(one):
    """A1 — 문서 하나의 구조 반영: 바꿀 것이 없는 계획인데 다른 이름의 기관 자리가 남았으면 「이미 맞음」 으로 끝내지 않고 그 까닭으로 멈춘다(반영 기록 · 한 자리만 반영한 기록은 그대로)."""
    one.config_confirm("t", V2)
    old, part = {"values": V3, "rev": 0}, [{"values": V3, "only": "g1"}]
    one.divs["t"].update(applied=dict(old), partial=list(part))
    one.apply_code, one.named = "nothing", 2
    X.start("t", {"from": "frame"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "named" and rec["end"]["text"].startswith("멈춤 — 연차보고서에 프로젝트 구성에 없는 기관 이름이 적힌 자리가 2곳 남아 있습니다")
    assert one.divs["t"]["applied"] == old and one.divs["t"]["partial"] == part and X.status_of("t")["stages"][2]["left"] == 2


def test_a_changed_current_year_is_not_counted_as_fitted(one):
    """A2 — 당해 차년도만 바꿔도 구조 반영은 끝난 것이 아니다(연차보고서의 「N단계-N차년도」 자리가 그 값으로 맞춰진다). 확정의 유효성은 전처럼 당해 차년도를 빼고 본다."""
    one.config_confirm("t", V2)
    X.start("t", {"from": "frame"})
    assert _done("t")["status"] == "done"
    one.divs["t"]["input"] = {**V2, "current": 2}
    v = X.status_of("t")["stages"]
    assert v[1]["left"] == 0 and v[2]["left"] == 2 and not v[2]["steps"][1]["done"]   # 확정은 그대로 유효 · 구조 반영은 다시
    one.calls.clear()
    X.start("t", {"from": "frame"})   # 전에는 「남은 단계가 없습니다」
    rec = _done("t")
    assert rec["status"] == "done" and [c[0] for c in one.calls if c[0] in ("plan", "apply")] == ["plan", "apply"] and one.divs["t"]["applied"]["values"]["current"] == 2
    assert X.status_of("t")["stages"][2]["left"] == 0
    assert not U.fit_done(_div(applied={"values": {**V2, "current": 2}})) and U.fit_done(_div({**V2, "current": 2}, applied={"values": {**V2, "current": 2}}))
    assert U.fit_done(_div({k: v for k, v in V2.items() if k != "current"}, applied={"values": V2}))   # 당해 차년도가 없는 값 = 1(프로파일의 기본값)
    assert not U.fit_done(_div(applied={"values": V2}, partial=[{"values": {**V2, "current": 3}}])) and U.confirm_valid({**V2, "current": 2}, {"values": V2})


def test_added_places_and_a_newer_plan_come_before_an_old_structure_confirmation(one):
    """A3 — 추가한 자리(hints)가 바뀌면 옛 구조 확인은 지금 후보의 것이 아니다 · 지금 문서의 전체 계획에 바뀔 것이 있으면 지난 반영 기록보다 그 계획이 먼저다."""
    one.config_confirm("t", V2)
    one.apply_code = "nothing"   # 구조가 이미 맞아 확인만 한 문서
    X.start("t", {"from": "frame"})
    assert _done("t")["status"] == "done" and one.divs["t"]["applied"]["adopted"] and X.status_of("t")["stages"][2]["left"] == 0
    one.hints = ["p9"]   # 그 뒤 추가한 자리를 더했다
    assert X.status_of("t")["stages"][2]["left"] == 2
    one.apply_code = "ok"
    one.calls.clear()
    X.start("t", {"from": "frame"})   # 전에는 「남은 단계가 없습니다」(「이미 프로젝트 구성에 맞습니다」)
    rec = _done("t")
    assert rec["status"] == "done" and [c[0] for c in one.calls if c[0] in ("plan", "apply")] == ["plan", "apply"] and one.divs["t"]["applied"]["hints"] == ["p9"]
    cf = {"values": V2, "at": 1}
    plan = {"planId": "p", "baseRev": 3, "only": None, "skip": [], "summary": {"groups": 1, "changes": 0, "applied": 1, "added": 0, "removed": 1, "deleted": 0}}
    st = lambda key, div: U.state(key, _ctx(div), "single")  # noqa: E731
    done = _div(confirmed=cf, applied={"values": V2, "rev": 4, "adopted": True})
    assert st("apply", done)["st"] == "done" and st("plan", done)["st"] == "done"
    assert st("apply", {**done, "plan": plan}) == {"st": "todo", "text": ""}   # 전에는 「이미 프로젝트 구성에 맞습니다」
    assert st("plan", {**done, "plan": plan}) == {"st": "done", "text": "맞출 자리 1곳 · 항목 추가 0 · 지움 1 · 글 바꿈 0 · 지워지는 글 문단 0"}   # 전에는 글 없는 끝남
    assert st("apply", {**done, "plan": plan, "stale": True})["st"] == "done" and st("apply", {**done, "plan": {**plan, "only": "g1"}})["st"] == "done"   # 낡은 계획 · 한 자리만의 계획은 그 근거가 아니다
    assert st("apply", {**done, "plan": {**plan, "summary": {"groups": 0, "changes": 0, "already": 3}}})["st"] == "done"
    assert st("apply", {**done, "hints": ["p9"]})["st"] == "todo" and st("apply", {**done, "hints": ["p9"], "applied": {**done["applied"], "hints": ["p9"]}})["st"] == "done"


def test_excluded_places_are_recorded_and_lifting_them_plans_again(one):
    """A4 — 「반영에서 빼기」 로 뺀 자리는 반영 기록에 남는다: 그 자리를 풀면(뺀 자리 없음을 알려 준 시작) 다시 계획하고, 뺀 자리를 모르는 화면이 시작한 실행은 지난 반영이 뺀 자리를 그대로 둔다."""
    one.config_confirm("t", V2)
    X.start("t", {"from": "frame", "skip": ["k1"]})
    assert _done("t")["status"] == "done" and one.divs["t"]["applied"]["skip"] == ["k1"]
    for body in ({"from": "frame"}, {"from": "frame", "skip": ["k1"]}, {"from": "frame", "skip": ["k1", "k2"]}):   # 뺀 자리를 모름 · 같은 자리 · 더 뺌 — 다시 볼 것이 없다
        with pytest.raises(X.Refuse) as e:
            X.start("t", body)
        assert e.value.reason == "noWork", body
    one.calls.clear()
    X.start("t", {"from": "frame", "skip": []})   # 뺀 자리를 풀었다 — 전에는 「남은 단계가 없습니다」
    rec = _done("t")
    assert rec["status"] == "done" and [c for c in one.calls if c[0] == "plan"] == [("plan", "t", ())] and one.divs["t"]["applied"]["skip"] == [] and rec["end"]["text"] == "끝남 — 반영 완료 · 편집 차례 2"
    one.divs["t"]["applied"]["skip"] = ["k7"]
    one.divs["t"]["input"] = {**V2, "current": 2}   # 다시 맞출 까닭이 생김(당해 차년도) — 뺀 자리를 모르는 화면(첫 화면의 대시보드)이 시작
    one.calls.clear()
    X.start("t", {"from": "frame"})
    rec = _done("t")
    assert rec["status"] == "done" and [c for c in one.calls if c[0] == "plan"] == [("plan", "t", ("k7",))] and rec["end"]["text"].endswith(" · 반영에서 뺀 자리 1곳은 그대로")
    assert not U.fit_done({**_div(applied={"values": V2, "skip": ["k1"]}), "excl": []}) and U.fit_done({**_div(applied={"values": V2, "skip": ["k1"]}), "excl": ["k1", "k2"]}) and U.fit_done(_div(applied={"values": V2, "skip": ["k1"]}))


def test_the_structure_is_fitted_only_with_the_input_confirmed_inside_the_fence(one, monkeypatch):
    """A5 — 확정 검사 뒤 · 울타리를 기다리는 사이 입력이 바뀜: (가) 확정하지 않은 값이면 문서를 바꾸지 않고 멈춘다(계획 요청이 옛 값으로 그 입력을 덮지도 않는다)
    (나) 다른 문서에서 새 값을 확정했으면 그 값으로 맞춘다(옛 값을 되쓰지 않는다) (다) 입력의 판을 읽은 뒤 계획 사이에 또 바뀌면 계획하지 않고 멈춘다."""
    one.config_confirm("t", V2)
    _at_fence(monkeypatch, lambda: one.divs["t"].update(input=V3))
    X.start("t", {"from": "frame"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "notConfirmed" and "그 사이 프로젝트 구성 값이나 확정이 바뀌었습니다" in rec["end"]["text"]
    assert one.divs["t"]["input"] == V3 and one.rev["t"] == 0 and not [c for c in one.calls if c[0] in ("plan", "apply")] and not X.FENCE and not X.NOTICE   # 전에는 [3] 을 [2] 로 되쓰고 반영했다
    one.config_confirm("t", V2)
    _at_fence(monkeypatch, lambda: one.config_confirm("t", V4))
    X.start("t", {"from": "frame"})
    rec = _done("t")
    assert rec["status"] == "done", rec["end"]
    assert one.divs["t"]["input"] == V4 and one.divs["t"]["applied"]["values"] == V4 and one.divs["t"]["confirmed"]["values"] == V4   # 전에는 계획 요청이 [2] 를 되써 [4] 가 사라졌다
    one.config_confirm("t", V2)
    one.calls.clear()
    one.on_plan = lambda: one.divs["t"].update(input=V3)
    X.start("t", {"from": "frame"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "stale" and ("planStale", "t") in one.calls and not [c for c in one.calls if c[0] == "apply"] and one.divs["t"]["input"] == V3


def test_reading_the_values_never_overwrites_an_input_saved_meanwhile(one):
    """A6 — 「구성 읽기」 는 입력이 아직 비어 있을 때만 읽은 값을 저장한다: 읽는 사이 다른 화면이 확정한 입력을 덮지 않는다."""
    one.job_key = "plan_fit"
    one.divs["t"]["input"] = None
    one.on_save = lambda: one.config_confirm("t", V4)   # 문서에서 값을 읽는 사이 다른 화면이 [4] 를 확정
    X.start("t", {"from": "config", "only": "read"})
    rec = _done("t")
    assert rec["status"] == "done" and one.divs["t"]["input"] == V4 and one.divs["t"]["confirmed"]["values"] == V4 and ("kept", "t") in one.calls and ("save", "t") not in one.calls   # 전에는 [2] 로 되써 입력과 확정이 갈렸다
    assert [(s["key"], s["status"]) for s in rec["steps"]] == [("read", "nothing")] and "읽은 값으로 바꾸지 않았습니다" in rec["steps"][0]["text"]


def test_the_input_is_saved_only_while_empty_and_planned_only_at_its_own_version(client):
    """A5 · A6 의 문 — 진짜 서버: 입력이 비어 있을 때만 저장(같은 프로젝트의 다른 문서가 먼저 저장했으면 그 값을 받는다 — 프로젝트 저장소의 한 잠금 안에서) · 값 없는 계획은 저장된 입력 그대로, 그 입력의 판일 때만."""
    from app import server
    a, b = (client.post("/api/docs?new=1", files={"file": (name, M.REPORT_FORM.read_bytes())}).json()["docId"] for name in ("가.hwpx", "나.hwpx"))
    for d in (a, b):
        assert client.put(f"/api/works/{d}/task", json={"kind": "rnd", "file": "report", "job": "report_fit", "project": "같은 과제"}).status_code == 200
    one, two = server.PROFILE.norm_values(M.SMALL_VALUES), server.PROFILE.norm_values({**M.SMALL_VALUES, "orgs": {**M.SMALL_VALUES["orgs"], "joint": ["가나대", "마바연"]}})
    assert unit_steps.div_facts(a)["input"] is None and unit_steps.div_facts(a)["hash"] is None
    got = unit_steps.config_save(a, one, if_empty=True)
    assert got.code == "ok" and got.data["saved"] is True and unit_steps.div_facts(a)["input"] == one
    got = unit_steps.config_save(a, two, if_empty=True)   # 입력이 이미 있다 — 덮지 않는다
    assert got.code == "nothing" and got.data["saved"] is False and unit_steps.div_facts(a)["input"] == one
    got = unit_steps.config_save(b, two, if_empty=True)   # 이 문서의 입력은 비어 있었지만 프로젝트의 입력이 이미 있다 — 그 값을 받는다(전의 조건 없는 저장은 프로젝트의 입력을 덮었다)
    assert got.code == "nothing" and unit_steps.div_facts(b)["input"] == one and unit_steps.div_facts(a)["input"] == one
    assert "saved" not in client.put(f"/api/docs/{b}/divisions/settings", json={"values": two}).json() and unit_steps.div_facts(a)["input"] == two   # 조건 없는 저장(화면)은 전과 같다 — 공유 입력이 바뀐다
    h = unit_steps.div_facts(a)["hash"]
    bad = unit_steps.division_plan(a, None, expect="0" * len(h))
    assert bad.code == "stale" and "그 사이에 바뀌었습니다" in bad.text and unit_steps.div_facts(a)["plan"] is None and unit_steps.div_facts(a)["input"] == two
    ok = unit_steps.division_plan(a, None, expect=h)
    assert ok.code == "ok" and ok.data["settingsHash"] == h and ok.data["values"] == two and unit_steps.div_facts(a)["input"] == two and unit_steps.div_facts(a)["plan"]["planId"] == ok.data["planId"]


# ---- 조정과 유료 호출(B1 ~ B4)
def test_the_adjust_door_sends_an_empty_plan_set_as_it_is(monkeypatch):
    """B1 — 「계획은 반영하지 않고 자리 맞춤 · 확실한 종속만」(빈 {})을 그대로 보낸다 — 안 보내면 끝점이 그 사이 도착한 계획까지 고른다."""
    from app import tpl_agent_api
    seen = []
    monkeypatch.setattr(tpl_agent_api, "apply_plans", lambda doc_id, body: seen.append(body) or {"changed": [], "nothing": True, "rev": 7})
    assert [unit_steps.adjust_apply("d", 7, p).code for p in ({}, None, {"T1": 3.5})] == ["nothing"] * 3
    assert seen == [{"rev": 7, "plans": {}}, {"rev": 7}, {"rev": 7, "plans": {"T1": 3.5}}]


def test_adjust_checks_the_judgement_again_inside_the_fence(std, monkeypatch):
    """B2 — 울타리를 기다리는 사이 헤딩을 다시 뽑았으면(판정 전의 그래프) 그 위에 반영하지 않는다 · 반영은 판정을 본 그 헤딩 그래프의 표시와 함께 건다."""
    std.hl = std.tl = "done"
    std.place, std.graph = 1, [3, 11.5]
    _at_fence(monkeypatch, lambda: setattr(std, "hl", "none"))
    X.start("t", {"from": "heads", "only": "adjust"})
    rec = _done("t")
    assert rec["status"] == "left" and not [c for c in std.calls if c[0] == "adjust"] and "헤딩 LLM 판정이 먼저입니다" in rec["end"]["text"]   # 전에는 자리 맞춤을 반영한 뒤에야 남겼다
    std.hl = "done"
    X.start("t", {"from": "heads", "only": "adjust"})
    rec = _done("t")
    assert rec["status"] == "done" and std.graphs == [[3, 11.5]] and [c[3] for c in std.calls if c[0] == "adjust"] == [{}] and std.seen[-1] == ("adjust", "", True)


def test_a_finished_llm_job_is_judged_again_instead_of_being_paid_twice(std):
    """B3 — (가) 이미 돌던 표 판정(LLM)이 답을 냈으면 기다린 뒤 다시 걸지 않는다 (나) 헤딩 LLM 판정의 이어 돌리기가 같이 부른 표 판정이 답을 못 냈으면 같은 실행의 표 줄이 또 부르지 않는다(다음 실행은 다시)."""
    std.hl = "done"
    std._go("t", "heads", lambda: setattr(std, "tl", "done"))   # 다른 화면이 건 표 판정(LLM)이 돌고 있다
    std.calls.clear()
    X.start("t", {"from": "tables"})
    rec = _done("t")
    assert rec["status"] == "done" and std.calls.count(("tablesLlm", "t")) == 1 and ("heads", "t") not in std.calls   # 한 번 걸어 봤고(자리가 참) 기다린 뒤에는 걸지 않았다 — 전에는 같은 표를 다시 유료로 판정했다
    std.hl = std.tl = "none"
    std.chain_tl = "failed"
    std.calls.clear()
    X.start("t", {"from": "heads", "to": "tables"})
    rec = _done("t")
    assert rec["status"] == "left" and ("llm", "t") in std.calls and ("tablesLlm", "t") not in std.calls   # 전에는 뒤의 표 줄이 같은 표를 다시 불렀다
    assert "다시 부르지 않음" in rec["left"][-1]["what"] and "같이 부른 표 판정(LLM)은 답을 내지 못했습니다" in rec["end"]["text"]
    X.start("t", {"from": "tables"})   # 다음 실행(사람이 다시 누름)은 다시 부른다
    assert _done("t")["status"] == "done" and std.calls.count(("tablesLlm", "t")) == 1 and std.tl == "done"


def test_no_paid_call_starts_after_a_stop_and_a_persons_stop_ends_the_run(std):
    """B4 — (가) 조정이 분석 상태를 읽는 사이 「멈춤」 이 오면 새 유료 호출(서식 정리 계획 받기)을 내지 않는다 (나) 사람이 문서 진행표에서 그 작업을 멈췄으면 실행도 멈춘다(남은 템플릿의 계획을 다시 유료로 부르지 않는다)."""
    std.hl = std.tl = "done"
    std.tpls.update({"T1": {"state": "none"}, "T2": {"state": "none"}})
    reads = []

    def stop_at_the_handlers_read():   # 실행 안의 둘째 읽기 = 조정의 처리 함수가 제 차례의 멈춤 검사 뒤에 분석 상태를 읽는 때
        if "t" in X.RUNS:
            reads.append(1)
            if len(reads) == 2:
                X.stop("t")
    std.on_analysis = stop_at_the_handlers_read
    X.start("t", {"from": "heads", "only": "adjust"})
    rec = _done("t")
    assert rec["status"] == "stopped" and ("formats", "t") not in std.calls   # 전에는 새 「서식 정리 계획 받기」 를 보낸 뒤에야 멈췄다
    std.on_analysis = None
    std.only_plans, std.person_stop = {"T1"}, True   # T1 의 계획만 받은 채 사람이 그 작업을 멈춤
    X.start("t", {"from": "heads", "only": "adjust"})
    rec = _done("t")
    assert rec["status"] == "stopped" and std.calls.count(("formats", "t")) == 1 and not [c for c in std.calls if c[0] == "adjust"]   # 전에는 남은 템플릿(T2)의 계획을 다시 불렀다


def test_only_the_job_this_run_started_is_waited_for(std, monkeypatch):
    """B4 — 기다리는 것은 내가 건 작업뿐: 내 표 판정이 끝난 자리에서 다른 화면의 작업이 돌기 시작해도 그것을 기다리거나 멈추지 않는다."""
    monkeypatch.setitem(X.WAIT, "llm", 1.0)
    std.hl, std.swap = "done", 99
    X.start("t", {"from": "tables"})
    rec = _done("t")
    assert rec["status"] == "done", rec["end"]   # 전에는 남의 작업이 끝나기를 기다리다 시간 초과로 멈췄다
    assert ("stop", "t") not in std.calls and std.jobs["t"]["started"] == 99 and std.jobs["t"]["status"] == "running" and std.tl == "done"


# ---- 실행하지 않고 남기는 「끝남」(C1 · C2) · 그 밖(P2)
def test_run_decisions_read_fresh_state_not_the_two_second_value(std):
    """C1 — 시작의 「남은 일 없음」 · 묶음 경계 · 묶음 건너뜀은 새로 읽은 분석 상태로(문의 2초 값은 조회에만): 같은 문서 차례에 도착한 서식 계획을 못 보고 「남은 단계가 없습니다」 로 끝내지 않는다."""
    std.keep = True
    std.hl = std.tl = "done"
    assert _stage(X.status_of("t"), "heads")["left"] == 0
    std.tpls["T1"] = {"state": "planned", "at": 1, "change": 2}   # 같은 문서 차례에 두 줄을 바꿀 서식 계획이 도착
    assert _stage(X.status_of("t"), "heads")["left"] == 0   # 조회는 잠깐 든 값 그대로(곧 새로 읽는다)
    flags, read0 = [], std.analysis
    std.analysis = lambda doc, fresh=True: (flags.append(fresh), read0(doc, fresh))[1]
    X.start("t", {"from": "heads"})   # 전에는 「남은 단계가 없습니다」
    rec = _done("t")
    assert rec["status"] == "done" and [c[3] for c in std.calls if c[0] == "adjust"] == [{"T1": 1}]
    std.tl = "none"
    std.tpls["T2"] = {"state": "planned", "at": 3, "change": 1}
    std.calls.clear()
    X.start("t", {"from": "heads", "to": "tables"})   # 묶음 경계도 — 헤딩 묶음을 건너뛰고 표만 하지 않는다
    rec = _done("t")
    assert rec["status"] == "done" and [c[3] for c in std.calls if c[0] == "adjust"] == [{"T2": 3}] and ("tablesLlm", "t") in std.calls
    assert flags and all(flags)   # 시작 · 실행의 판단에는 잠깐 든 값을 한 번도 쓰지 않았다


def test_a_start_that_picks_only_a_persons_line_is_refused(one):
    """C2 — 줄 하나만(only) 고른 시작이 사람이 직접 하는 줄이면 아무 일 없이 「끝남」 으로 남기지 않고 까닭과 함께 거절한다(실행기가 하는 줄은 그대로)."""
    with pytest.raises(X.Refuse) as e:
        X.start("t", {"from": "frame", "only": "plan"})   # 전에는 확정도 계획도 없이 「끝남」
    assert e.value.reason == "pick" and e.value.message == "「변경 계획 보기」 은(는) 사람이 직접 하는 단계입니다 — 서버가 대신 진행하지 않습니다(문서 화면에서 합니다)" and "t" not in X.RUNS and not one.files
    X.start("t", {"from": "frame", "only": "apply"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "notConfirmed"


def test_a_relay_start_that_picks_only_a_persons_line_is_refused_too(fit):  # noqa: F811
    """C2 는 열려 있는 틀에도 닿는다 — 이관형의 「구성 불러오기」(사람이 고르는 선택 줄)만 고른 시작도 거절한다(전에는 아무 일 없이 「끝남」)."""
    with pytest.raises(X.Refuse) as e:
        X.start("t", {"from": "frame", "only": "configLoad"})
    assert e.value.reason == "pick" and "「구성 불러오기」" in e.value.message and "t" not in X.RUNS


def test_the_end_text_names_undecided_headings_even_when_nothing_is_left_to_apply(std):
    """P2 — 반영할 것이 없어 조정 줄이 끝났어도 헤딩 판정의 미판정은 끝 글에 남긴다(수 · 다시 판정할 곳)."""
    std.hl = std.tl = "done"
    std.undecided = 1
    X.start("t", {"from": "heads", "only": "adjust"})
    rec = _done("t")
    assert rec["status"] == "done" and rec["end"]["text"] == "끝남 — 반영할 것이 남지 않았습니다 · 남긴 것: 헤딩 판정의 미판정 1곳(LLM 구간 검증 실패 — 「단계별 실행」 의 헤딩 판정을 다시)"


def test_division_facts_are_read_only_for_the_lines_that_use_them(fit, monkeypatch):  # noqa: F811
    """P2 — 구성 재료는 그것을 읽는 줄(구성 추출 · 구성 반영 · 다시 문서 검토)이 있을 때만 읽는다: 사람이 고르는 「구성 불러오기」 뿐인 정의의 상태 조회가 구성을 건드리지 않는다
    (읽으면 그 문서의 입력이 프로젝트의 공유 입력으로 올라갈 수 있다). 붙박이 이관은 전과 같다."""
    reads, div0 = [], fit.div_facts
    fit.div_facts = lambda doc: (reads.append(doc), div0(doc))[1]
    X.status_of("t")
    assert sorted(set(reads)) == ["s", "t"]
    task = copy.deepcopy(S.definition("plan_to_report"))
    task["stages"] = [g for g in task["stages"] if g["id"] in ("review", "frame")]
    task["stages"][1]["steps"] = [s for s in task["stages"][1]["steps"] if s["key"] == "configLoad"]
    monkeypatch.setattr(S, "definition", lambda job: task if job == "plan_to_report" else None)
    reads.clear()
    v = X.status_of("t")
    assert v["stages"][1]["server"] and [s["key"] for s in v["stages"][1]["steps"]] == ["configLoad"] and reads == []   # 전에는 두 문서의 구성 재료를 읽었다


# ---- 바쁨 막이 — 문서 하나의 서버 실행이 도는 동안
def test_people_cannot_start_the_same_work_while_a_single_document_run_owns_the_document(client, monkeypatch):
    """문서 하나의 서버 실행이 도는 문서 — 사람이 누른 헤딩 추출 · 표 판정(LLM) · LLM 검증·보완 · 서식 정리 계획 받기 · 조정 「모두 반영」 · 프로젝트 구성 변경 계획 · 반영은 409(읽기는 된다 · 그 실행의 스레드는 지나간다).
    다른 틀(이관형)의 실행이 도는 동안 · 도는 실행이 없을 때는 전과 같다."""
    from app import analysis_api, heading_runs, server
    doc = client.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    assert client.put(f"/api/works/{doc}/task", json={"kind": "rnd", "file": "report", "job": "report_fit", "project": "시험 과제"}).status_code == 200
    assert client.post(f"/api/docs/{doc}/divisions/confirm", json={"values": M.SMALL_VALUES}).status_code == 200

    def never(*a, **k):   # 막이가 빠졌을 때 진짜 작업(유료 LLM)을 걸지 않게
        raise AssertionError("바쁨 막이가 없어 진짜 헤딩 작업을 걸 뻔했습니다")
    monkeypatch.setattr(analysis_api, "start_chain", never)
    monkeypatch.setattr(heading_runs, "start", never)
    d = f"/api/docs/{doc}"

    def own(task):
        X.BUSY[doc] = doc
        X.RUNS[doc] = X.Run({"n": 1, "scope": ["시험 과제", task["job"], 1], "docs": {"target": {"id": doc}}, "steps": [], "stages": []}, task, {}, None)
        return X.RUNS[doc]
    try:
        run = own(S.definition("report_fit"))
        got = [client.post(f"{d}/headings", json={"first": True}), client.post(f"{d}/headings", json={"stage": 3, "llm": True}), client.post(f"{d}/headings", json={"stage": 2, "llm": True}),
               client.post(f"{d}/analysis/llm", json={}), client.post(f"{d}/analysis/llm", json={"only": "formats"}), client.post(f"{d}/outline/agent/apply", json={"rev": 0}),
               client.post(f"{d}/divisions/plan", json={}), client.post(f"{d}/divisions/apply", json={"planId": "x"})]
        assert [r.status_code for r in got] == [409] * len(got) and all("도는 중" in r.text for r in got), [(r.status_code, r.text[:60]) for r in got]
        assert client.get(f"{d}/analysis").status_code == 200 and client.get(f"{d}/divisions").status_code == 200 and client.get(f"{d}/headings").status_code == 200   # 읽기는 된다
        out = []
        th = threading.Thread(target=lambda: out.append(X.busy_other(doc, "single")))   # 다른 스레드(사람의 요청)
        th.start()
        th.join()
        run.threads.add(threading.get_ident())   # 그 실행의 스레드 — 실행이 스스로 부르는 같은 끝점은 지나간다
        server._flow_busy_other(doc, "single")
        assert out == [X.BUSY_TEXT] and X.busy_other(doc, "single") == "" and X.busy_other("nope", "single") == ""
        own(S.definition("plan_to_report"))   # 다른 틀의 실행 — 이 막이는 문서 하나의 실행만(이관형 · 취합의 실행 동안 이 끝점들은 전과 같다)
        assert X.busy_other(doc) == X.BUSY_TEXT and X.busy_other(doc, "single") == ""
        assert client.post(f"{d}/divisions/plan", json={}).status_code == 200
    finally:
        X.RUNS.clear()
        X.BUSY.clear()
    assert client.post(f"{d}/divisions/plan", json={}).status_code == 200   # 도는 실행이 없으면 그대로
