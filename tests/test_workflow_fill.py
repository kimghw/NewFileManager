"""3단계 「내용 넣기」 · 4단계 「문서 정리」 를 서버 실행기가(spec_워크플로우 ② §18-4 「차례 실행기」 · §18-12 ② · ③ — app/workflow_exec.py 의 넣기 절 · app/workflow_units.py 의 상태 식):
가짜 문으로 차례(빈 자리 검토 → 표 대응) · 무르기(답 뒤 새 계획) · 마지막 계획 · 낡은 계획은 한 번만 다시 · 정상 0건 · 유료 시도 기록(결과 불명이면 다시 안 부름) · 울타리 안의 반영 ·
LLM 을 못 씀 · 서비스 실패는 남기고 계속 · 막는 까닭은 멈춤 · 「문서 정리」 는 「내용 넣기」 뒤 · 끝 글 = 화면 실행의 글을 본다. 실제 쌍은 tests/test_unit_steps.py."""
import copy
import json
import threading
import time

import pytest

from app import unit_steps
from app import workflow_exec as X
from app import workflow_state as S
from app import workflow_units as U
from test_workflow_exec import Fake

Outcome = unit_steps.Outcome
VALS = {"stages": [2], "orgs": {"joint": []}, "current": 1}
PATTERNS = [{"key": "tables", "name": "작성 요령 표"}, {"key": "notes", "name": "※ 안내"}]


class FillFake(Fake):
    """가짜 문 — 1 · 2단계는 끝난 쌍(분석 · LLM · 구성 확정 · 구조 반영)에서 넣기 · 정리의 끝점을 흉내 낸다. calls 에 부른 차례가 남는다."""

    def __init__(self):
        super().__init__()
        self.heads.update(s=True, t=True)
        self.llm.update(s=True, t=True)
        self.divs = {"s": {"input": VALS, "applied": {"values": VALS, "rev": 0}, "confirmed": None, "sharing": None, "read": None},
                     "t": {"input": VALS, "applied": {"values": VALS, "rev": 0}, "confirmed": {"values": VALS, "at": 0}, "sharing": None, "read": None}}
        self.L = {"error": None, "from": {"reasons": []}, "to": {"reasons": []}, "counts": {"paired": 2, "ambiguous": 1, "toOnly": 0, "fromOnly": 0},
                  "fixed": {"counts": {"tables": 1, "tablesOpen": 0, "mapOpen": 0}, "todo": 1, "error": None}, "llm": None, "kept": {"applied": 0}}
        self.rev, self.todo, self.gaps_open, self.maps_open, self.after_gaps = 0, 3, 2, 0, 1   # 빈 자리 검토가 새 표 쌍을 정해 표 대응이 1개 열린다(차례가 거꾸로면 그 표가 빠진다)
        self.gaps_todo = None                     # 빈 자리 검토 뒤의 넣을 것(첫 계획의 0 을 마지막 계획이 바꾸는 시험)
        self.plan, self.filled, self.clean, self.n = None, None, 4, 0
        self.stale, self.llm_fail, self.gaps_fail, self.fenced = 0, False, False, []
        self.old, self.gaps_units_fail = False, False   # 목적 문서의 분석이 구조 반영 전 스크립트 결과(안전망) · 빈 자리 검토가 200 인데 모든 장이 실패

    # 읽기
    def fill_ver(self, doc):
        return json.dumps([self.rev, self.gaps_open, self.maps_open, bool(self.L["llm"]), self.L["counts"]["paired"]])

    def fill_facts(self, doc):
        if doc != "t":
            return None
        p = self.plan
        return {"links": copy.deepcopy(self.L), "plan": None if p is None else {**p, "fresh": p["ver"] == self.fill_ver(doc)}, "heads": {"old": self.old, "kept": False, "stale": self.old},
                "cleanup": {"counts": {"total": self.clean, "tables": self.clean}, "patterns": PATTERNS, "error": ""}, "filled": self.filled}

    def links(self, doc):
        return Outcome("ok", "", copy.deepcopy(self.L))

    # 동기 일
    def _fenced(self):
        self.fenced.append((X.FENCE.get("t") or {}).get("thread") == threading.get_ident())

    def links_llm(self, doc):
        self.calls.append(("linksLlm", doc))
        if self.llm_fail:
            return Outcome("error", "LLM 이 답하지 않음")
        self.L["llm"] = {"units": [{"call": {}}], "tables": {}, "job": None}
        self.L["counts"].update(ambiguous=0, paired=self.L["counts"]["paired"] + 1)
        return Outcome("ok", "", copy.deepcopy(self.L))

    def fill_plan(self, doc):
        self.calls.append(("plan", doc))
        self.n += 1
        self.plan = {"planId": f"p{self.n}", "todo": self.todo, "ver": self.fill_ver(doc), "body": {"counts": {"todo": self.todo}}, "tables": {"counts": {"cells": 0, "rows": 0}},
                     "fixed": {"counts": {"cells": 0, "labels": 0}}, "maps": {"counts": {"open": self.maps_open}}, "gaps": {"counts": {"open": self.gaps_open}}}
        return Outcome("ok", "", copy.deepcopy(self.plan))

    def fill_gaps(self, doc):
        self.calls.append(("gaps", doc))
        if self.gaps_fail:
            return Outcome("error", "LLM 이 답하지 않음")
        if self.gaps_units_fail:   # 끝점은 200 — 장마다의 호출이 모두 실패(표 짝 하나는 저장됨: 계획을 새로 세워야 한다)
            self.maps_open += self.after_gaps
            return Outcome("ok", "", {"asked": 2, "found": {"tables": 1, "slots": 1}, "tables": {"paired": 0}, "slots": {"filled": 0}, "units": [{"title": "1.", "error": "시간 초과"}, {"title": "2.", "error": "시간 초과"}]})
        self.gaps_open, self.maps_open = 0, self.maps_open + self.after_gaps
        if self.gaps_todo is not None:
            self.todo = self.gaps_todo
        return Outcome("ok", "", {"asked": 1, "found": {"tables": 1, "slots": 1}, "tables": {"paired": 1}, "slots": {"filled": 1}})

    def fill_maps(self, doc):
        self.calls.append(("maps", doc))
        n, self.maps_open = self.maps_open, 0
        return Outcome("ok", "", {"mapped": n, "tables": [{}] * n})

    def fill_apply(self, doc, plan_id):
        self.calls.append(("apply", plan_id))
        self._fenced()
        if self.plan is None or self.plan["planId"] != plan_id or self.plan["ver"] != self.fill_ver(doc):
            return Outcome("stale", "계획이 없거나 바뀌었습니다 — 다시 계획하세요")
        if self.stale:
            self.stale -= 1
            self.plan = None
            return Outcome("stale", "계획을 세운 뒤 문서가 바뀌었습니다 — 다시 계획하세요")
        if not self.plan["todo"]:
            self.plan, self.filled = None, {"nothing": True}
            return Outcome("nothing", "넣을 것이 없습니다", {"nothing": True})
        self.rev, self.plan, self.filled, self.todo = self.rev + 1, None, {"nothing": False}, 0
        self.L["kept"]["applied"] = 3
        return Outcome("ok", "", {"body": {"blocks": 3}, "tables": {"filled": 2, "rowsAdded": 1}, "converted": {"converted": 0}})

    def cleanup_count(self, doc):
        return Outcome("ok", "", {"counts": {"total": self.clean, "tables": self.clean}, "patterns": PATTERNS, "rev": self.rev})

    def cleanup(self, doc, rev):
        self.calls.append(("cleanup", rev))
        self._fenced()
        if rev != self.rev:
            return Outcome("stale", "목록을 읽은 뒤 문서가 바뀌었습니다")
        n, self.clean, self.rev = self.clean, 0, self.rev + 1
        return Outcome("ok", "", {"done": {"tables": n, "skipped": []}})


@pytest.fixture
def fake(monkeypatch):
    f = FillFake()
    monkeypatch.setattr(X, "UNIT", f)
    monkeypatch.setitem(X.WAIT, "poll", 0.005)
    for k, v in (("settle", 0.02), ("poll", 0.005)):
        monkeypatch.setitem(X.FENCE_WAIT, k, v)
    X.RUNS.clear(); X.BUSY.clear(); X.LAST.clear()
    yield f
    _done("t", 5)
    X.RUNS.clear(); X.BUSY.clear(); X.LAST.clear()


def _done(target, seconds=5):
    t0 = time.time()
    while target in X.RUNS and time.time() - t0 < seconds:
        time.sleep(0.005)
    assert target not in X.RUNS, "실행이 끝나지 않았습니다"
    return X.last(target)


def _calls(f):
    return [c[0] for c in f.calls]


def test_fill_and_clean_run_in_the_fixed_order_with_the_screen_end_text(fake):
    """「이어서 한 번에」(3 → 4단계) — 자리 연결 → LLM 검토 → 넣기 계획 → 빈 자리 검토 → (무르기) 계획 → 표 대응 → (무르기) 계획 → 반영(울타리 안) → 작성요령 삭제(울타리 안)."""
    v = X.status_of("t")
    rows = {g["id"]: g for g in v["stages"]}
    assert rows["map"]["server"] and rows["map"]["left"] and rows["map"]["can"] and rows["clean"]["server"] and rows["clean"]["why"] == "3단계 「내용 넣기」 이 먼저입니다"
    assert [s["key"] for s in rows["map"]["steps"]] == ["link", "llm", "plan", "gaps", "tableMap", "apply"] and rows["map"]["steps"][0]["st"] == "now"
    X.start("t", {"from": "map", "to": "clean"})
    rec = _done("t")
    assert rec["status"] == "done", rec["end"]
    assert _calls(fake) == ["linksLlm", "plan", "gaps", "plan", "maps", "plan", "apply", "cleanup"]   # 빈 자리 검토가 연 표를 표 대응이 본다 · 답마다 계획을 새로
    assert fake.fenced == [True, True]   # 문서를 바꾸는 두 줄은 울타리 안에서(그 실행 스레드)
    assert rec["stages"][0]["text"] == "연결됨 3 · 빈 자리 검토 2/2 · 표 대응 1/1 · 본문 블록 3 · 표 칸 2 · 행 추가 1 · 템플릿 변환 0줄"   # 화면 taskRunMap 의 끝 글 그대로
    assert rec["stages"][1]["text"] == "작성 요령 표 4을(를) 지웠습니다" and rec["end"]["text"].startswith("끝남 — 연결됨 3")
    assert [(t["key"], t["status"]) for t in rec["tries"]] == [("llm", "saved"), ("gaps", "saved"), ("tableMap", "saved")] and all(t["pair"] == ["s", "t"] for t in rec["tries"])
    assert [s["key"] for s in rec["steps"]] == ["link", "llm", "plan", "gaps", "tableMap", "apply", "guide"] and rec["steps"][0]["text"].startswith("연결 목록 — 연결됨 2 · 확인 필요 1")
    after = {g["id"]: g for g in X.status_of("t")["stages"]}
    assert after["map"]["left"] == 0 and after["clean"]["left"] == 0 and after["clean"]["why"] == "남은 단계가 없습니다"   # 끝남은 문서의 결과로(반영 표식 · 지울 안내 0)


def test_a_stale_plan_is_planned_again_only_once(fake):
    fake.L["counts"]["ambiguous"], fake.gaps_open = 0, 0
    fake.stale = 1
    X.start("t", {"from": "map"})
    rec = _done("t")
    assert rec["status"] == "done" and _calls(fake) == ["plan", "apply", "plan", "apply"]   # 같은 입력으로 한 번만 다시 계획
    fake2 = FillFake()
    X.UNIT = fake2
    fake2.L["counts"]["ambiguous"], fake2.gaps_open, fake2.stale = 0, 0, 2
    X.start("t", {"from": "map"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "stale" and _calls(fake2) == ["plan", "apply", "plan", "apply"] and fake2.filled is None   # 둘째 충돌은 멈춤


def test_normal_zero_ends_without_a_plan_and_lets_the_clean_stage_run(fake):
    """정상 0건(막는 까닭 없이 낸 목록에 넣을 자리 0) — 계획 · 반영 없이 끝나고 「문서 정리」 로 간다(구성 맞추기와 따로 판정)."""
    fake.L["counts"].update(paired=0, ambiguous=0)
    fake.L["fixed"]["todo"] = 0
    assert U.state("plan", S.context(X.S.definition("plan_to_report"), fake.pair("t"), X._materials(fake.pair("t"), X.S.definition("plan_to_report")), llm=True, skip=()), "relay")["skipped"] is True
    X.start("t", {"from": "map", "to": "clean"})
    rec = _done("t")
    assert rec["status"] == "done" and _calls(fake) == ["cleanup"] and rec["stages"][0]["text"] == "남은 단계가 없습니다"   # 상태가 이미 끝 — 묶음을 건너뛰고 경계에서 다음 묶음으로
    assert rec["stages"][1]["text"] == "작성 요령 표 4을(를) 지웠습니다"
    # 묶음이 도는 경우(확인 필요가 남아 LLM 검토를 했지만 실패) — 넣기 계획 줄이 정상 0건으로 끝내고 계획 · 반영을 부르지 않는다
    fake2 = FillFake()
    X.UNIT = fake2
    fake2.L["counts"].update(paired=0, ambiguous=1)
    fake2.L["fixed"]["todo"], fake2.llm_fail = 0, True
    X.start("t", {"from": "map"})
    rec = _done("t")
    assert _calls(fake2) == ["linksLlm"] and rec["status"] == "left"
    assert rec["stages"][0]["text"] == "이어진 자리가 없어 넣을 내용이 없습니다(연결됨 0 · 확인 필요 1(비워 둠) · LLM 검토는 못 함(확인 필요한 자리는 비워 둠))"   # 화면 taskRunMap 의 linksNone 끝 글


def test_the_last_plan_decides_even_when_the_first_has_nothing(fake):
    """첫 계획의 넣을 것이 0 이어도 빈 자리가 열려 있으면 빈 자리 검토를 하고 그 뒤의 계획으로 정한다(② §18-12 ②)."""
    fake.L["counts"]["ambiguous"], fake.todo, fake.gaps_todo, fake.after_gaps = 0, 0, 2, 0
    X.start("t", {"from": "map"})
    rec = _done("t")
    assert _calls(fake) == ["plan", "gaps", "plan", "apply"] and rec["status"] == "done" and "본문 블록 3" in rec["stages"][0]["text"]


def test_nothing_to_put_is_confirmed_without_the_fence(fake):
    fake.L["counts"]["ambiguous"], fake.gaps_open, fake.todo = 0, 0, 0
    X.start("t", {"from": "map"})
    rec = _done("t")
    assert rec["status"] == "done" and fake.filled == {"nothing": True} and fake.fenced == [False]   # 넣을 것 0 — 문서는 안 바뀌어 울타리 없이 표식만
    assert rec["stages"][0]["text"] == "연결됨 2 · 넣을 것이 없습니다(이미 넣었거나 넣을 자리가 없음)"   # 화면 taskRunMap 의 「!p.todo」 끝 글


def test_a_paid_call_with_an_unknown_result_is_not_called_again(fake):
    """지난 실행이 같은 입력으로 빈 자리 검토를 부르다 끊겼다(시도만 적힘) — 「이어서」 는 저절로 다시 부르지 않고 남긴다. 다른 줄은 이어서 한다."""
    fake.L["counts"]["ambiguous"] = 0
    ver = fake.fill_ver("t")
    fake.files[("t", 1)] = {"v": 1, "n": 1, "boot": "deadbeef", "status": "running", "now": {"stage": "map", "key": "gaps", "note": "빈 자리 검토"}, "range": {"from": "map", "to": "map"},
                            "docs": {"target": {"id": "t"}, "source": {"id": "s"}}, "stages": [], "steps": [], "left": [],
                            "tries": [{"stage": "map", "key": "gaps", "pair": ["s", "t"], "ver": ver, "status": "started", "t0": 0}]}
    X.start("t", {"from": "map"})
    rec = _done("t")
    assert rec["n"] == 2 and "gaps" not in _calls(fake) and _calls(fake) == ["plan", "apply"] and rec["status"] == "left"
    assert "결과를 모릅니다" in rec["left"][0]["what"] and "「빈 자리 검토(LLM)」 단추로 다시" in rec["left"][0]["what"]
    assert X.record("t", 1)["status"] == "cut"


def test_without_llm_no_paid_call_and_the_lines_are_skipped(fake):
    fake.ok = False
    X.start("t", {"from": "map"})
    rec = _done("t")
    assert rec["status"] == "done" and _calls(fake) == ["plan", "apply"]
    assert rec["stages"][0]["text"] == "연결됨 2 · 확인 필요 1(비워 둠) · LLM 검토는 못 함(확인 필요한 자리는 비워 둠) · 빈 자리 검토는 못 함(그 자리는 비워 둠) · 본문 블록 3 · 표 칸 2 · 행 추가 1 · 템플릿 변환 0줄"


def test_a_failed_optional_llm_is_left_and_the_run_goes_on(fake):
    fake.llm_fail, fake.gaps_fail = True, True
    X.start("t", {"from": "map"})
    rec = _done("t")
    assert rec["status"] == "left" and rec["end"]["ok"] and rec["end"]["text"].startswith("남김 — 연결됨 2 · 확인 필요 1(비워 둠) · LLM 검토는 못 함")
    assert [x["key"] for x in rec["left"]] == ["llm", "gaps"] and _calls(fake) == ["linksLlm", "plan", "gaps", "plan", "apply"]   # 확실한 자리는 넣었다 · 부른 뒤에는 실패해도 새 계획으로
    assert [(t["key"], t["status"]) for t in rec["tries"]] == [("llm", "failed"), ("gaps", "failed")]


def test_blocking_reasons_halt_before_writing(fake):
    fake.L["to"]["reasons"] = ["notApplied"]
    X.start("t", {"from": "map"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "blocked" and rec["halt"]["text"] == "연결 목록을 낼 수 없습니다 — 연차보고서: 프로젝트 구성 반영 전" and not fake.calls


def test_the_clean_stage_waits_for_the_fill_stage(fake):
    X.start("t", {"from": "clean"})
    rec = _done("t")
    assert rec["status"] == "left" and rec["steps"][-1]["text"] == "3단계 「내용 넣기」 이 덜 끝났습니다" and not fake.calls


def test_stage_paid_approval_of_an_agent_card(fake):
    run = X.Run({"docs": {"target": {"id": "t"}}, "range": {"from": "map", "to": "map"}, "stopping": False}, X.S.definition("plan_to_report"), fake.pair("t"), {"paid": []})
    assert X._stage_paid_ok(run, "map") and not X._stage_paid_ok(run, "clean")   # 카드가 승인한 범위의 묶음
    run.approval = {"paid": [], "stagePaid": []}
    assert not X._stage_paid_ok(run, "map")
    run.approval = None
    assert X._stage_paid_ok(run, "map")   # 사람이 누른 실행


def test_fill_lines_follow_the_screen_rules(fake):
    task = S.definition("plan_to_report")
    pair = fake.pair("t")

    def lines():
        ctx = S.context(task, pair, X._materials(pair, task), llm=fake.ok, skip=())
        return {k: U.state(k, ctx, "relay") for k in ("link", "llm", "plan", "gaps", "tableMap", "apply", "guide")}
    st = lines()
    assert st["link"]["st"] == "todo" and st["link"]["text"].startswith("연결됨 2 · 확인 필요 1 · 후보 없음 0 · 원본에만 0 · 같은 이름 자리 1 · 같은 표 1") and "다음: 「LLM 검토」" in st["link"]["text"]
    assert st["llm"]["st"] == "todo" and st["plan"]["st"] == "todo" and st["apply"]["st"] == "todo" and st["guide"]["st"] == "todo" and "작성 요령 표 4" in st["guide"]["text"]
    fake.fill_plan("t")
    st = lines()
    assert st["plan"]["st"] == "done" and st["plan"]["text"].startswith("본문 3항목") and st["gaps"]["st"] == "todo" and st["apply"]["st"] == "todo"   # 넣을 것이 있는 지금 계획 — 반영이 남음
    fake.rev += 1   # 계획 뒤 문서가 바뀜 — 그 계획은 「지금 계획」 이 아니다
    st = lines()
    assert st["plan"]["st"] == "todo" and "바뀌었습니다" in st["plan"]["text"]
    fake.filled, fake.plan = {"nothing": False}, None
    st = lines()
    assert st["plan"]["st"] == "done" and st["apply"]["st"] == "done" and st["guide"]["st"] == "todo"   # 반영 표식 — 「내용 넣기」 의 끝 · 지울 안내가 남음
    fake.clean = 0
    assert lines()["guide"] == {"st": "done", "text": "지울 안내가 없습니다"}
    fake.ok = False
    fake.L["counts"]["ambiguous"] = 1
    st = lines()
    assert st["link"]["st"] == "done" and st["link"]["skipped"] and st["llm"]["skipped"]   # LLM 을 못 쓰면 「건너뜀」 — 남은 자리는 비워 둔다


# ---------------------------------------------------------------- astra 결과 검토(artifacts/fill_server_astra_2026-11-20/answer.md)로 더한 반례
def test_a_fresh_zero_plan_with_open_places_is_not_the_end(fake):
    """사람이 먼저 세운 계획이 넣을 것 0 · 빈 자리 열림 — 「내용 넣기」 의 끝이 아니다: 묶음을 건너뛰지 않고 빈 자리 검토 → 마지막 계획으로 정한 뒤 정리."""
    fake.L["counts"]["ambiguous"], fake.todo, fake.after_gaps = 0, 0, 0
    fake.fill_plan("t")
    fake.calls.clear()
    assert not U.fill_done(fake.fill_facts("t"))
    X.start("t", {"from": "map", "to": "clean"})
    rec = _done("t")
    assert _calls(fake) == ["plan", "gaps", "plan", "apply", "cleanup"] and rec["status"] == "done"


def test_an_optional_answer_where_every_unit_failed_is_left_and_the_plan_is_made_again(fake):
    """빈 자리 검토가 200 인데 모든 장이 실패 — 남김(시도 기록 failed) · 그래도 계획은 새로(그 사이 표 짝이 저장돼 표 대응이 열렸다)."""
    fake.L["counts"]["ambiguous"], fake.gaps_units_fail = 0, True
    X.start("t", {"from": "map"})
    rec = _done("t")
    assert rec["status"] == "left" and [x["key"] for x in rec["left"]] == ["gaps"] and _calls(fake) == ["plan", "gaps", "plan", "maps", "plan", "apply"]
    assert [(t["key"], t["status"]) for t in rec["tries"]] == [("gaps", "failed"), ("tableMap", "saved")]


def test_a_failed_safety_net_analysis_halts_before_linking(fake):
    """목적 문서의 분석이 구조 반영 전 스크립트 결과 — 다시 분석하다 실패하면 옛 분석으로 잇지 않고 멈춘다."""
    fake.old = True
    fake.fail.add("t")
    X.start("t", {"from": "map"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "failed" and "실패했습니다" in rec["halt"]["text"] and not fake.calls[1:] and fake.calls[0] == ("heads", "t")


def test_unknown_results_use_the_latest_record_of_that_call(fake):
    """같은 줄 · 같은 판의 시도는 새 기록부터 — 오래된 started 뒤에 saved 가 있으면 불명이 아니다 · 무관한 실행이 여럿 끼어도 놓치지 않는다."""
    ver = fake.fill_ver("t")
    rec = lambda n, tries: {"v": 1, "n": n, "boot": X.BOOT, "status": "done", "range": {"from": "map", "to": "map"}, "docs": {"target": {"id": "t"}}, "stages": [], "steps": [], "left": [], "tries": tries}  # noqa: E731
    fake.files[("t", 1)] = rec(1, [{"key": "gaps", "ver": ver, "status": "started"}])
    for n in range(2, 10):
        fake.files[("t", n)] = rec(n, [])
    run = X.Run(rec(10, []), X.S.definition("plan_to_report"), fake.pair("t"), None)
    assert X._tries_unknown(run, "gaps", ver) is True   # 무관한 실행 8개 뒤에도
    fake.files[("t", 9)] = rec(9, [{"key": "gaps", "ver": ver, "status": "saved"}])
    assert X._tries_unknown(run, "gaps", ver) is False and X._tries_unknown(run, "tableMap", ver) is False


def test_an_agent_card_cannot_widen_the_range_to_more_paid_stages(fake):
    """에이전트 카드(승인한 묶음이 적혀 있지 않음) — 묶음 하나만 도는 카드일 때만 그 묶음의 묶음째 유료를 허락한다(범위를 넓혀 유료 줄을 늘리지 못하게)."""
    X.start("t", {"from": "map", "to": "clean", "by": "agent", "paid": []})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "approval" and "linksLlm" not in _calls(fake)
    fake2 = FillFake()
    X.UNIT = fake2
    X.start("t", {"from": "map", "by": "agent", "paid": []})
    assert _done("t")["status"] == "done" and "linksLlm" in _calls(fake2)


def test_link_ends_without_an_llm_line_in_the_definition(fake):
    """조립한 정의에 자리 연결 LLM 검토 줄이 없으면 — 확인 필요는 비워 두고 자리 연결은 끝(막다른 길 없음)."""
    F = {**fake.fill_facts("t"), "lines": ["link", "plan", "apply"], "stages": {}}
    ctx = {"ready": True, "llm": True, "pair": {"source": {"role": "source", "title": "사업계획서", "id": "s", "facts": fake.facts("s")},
                                                 "target": {"role": "target", "title": "연차보고서", "id": "t", "facts": {**fake.facts("t"), "fill": F}}}}
    assert U.state("link", ctx, "relay")["st"] == "done"
    F["lines"].append("llm")
    assert U.state("link", ctx, "relay")["st"] == "todo"


# ---- 원본 문서에 놓는 줄(② §18-2 「원본 문서에 놓는 줄」 — 2026-11-20 사용자 「목적문서랑 원본 문서도 분리해서 따로 따로 하게」)
def _on(monkeypatch, **on):
    """붙박이 이관의 줄의 하는 문서를 바꾼 정의(조립한 정의가 그 줄을 원본 문서에도 놓은 꼴) — on = {줄 key: source | target | both}."""
    task = copy.deepcopy(S.definition("plan_to_report"))
    for g in task["stages"]:
        g["steps"] = [{**s, "on": on.get(s["key"], s["on"])} for s in g["steps"]]
    monkeypatch.setattr(S, "definition", lambda job: task if job == "plan_to_report" else None)


def test_guide_on_both_documents_cleans_each_document_after_the_fill(fake, monkeypatch):
    """「작성요령 삭제」 를 두 문서에 같이 놓은 정의 — 「내용 넣기」 의 끝 뒤에, 문서마다 따로 세고 울타리 안에서 지운다(원본 → 목적) · 끝 글에 문서 이름."""
    _on(monkeypatch, guide="both")
    left = {"s": 2, "t": 4}
    fake.cleanup_count = lambda doc: Outcome("ok", "", {"counts": {"total": left[doc], "tables": left[doc]}, "patterns": PATTERNS, "rev": fake.rev})

    def cleanup(doc, rev):
        fake.calls.append(("cleanup", doc))
        fake.fenced.append((X.FENCE.get(doc) or {}).get("thread") == threading.get_ident())
        n, left[doc] = left[doc], 0
        if doc == "t":
            fake.clean = 0
        return Outcome("ok", "", {"done": {"tables": n, "skipped": []}})
    fake.cleanup = cleanup
    line = next(s for s in {g["id"]: g for g in X.status_of("t")["stages"]}["clean"]["steps"] if s["key"] == "guide")
    assert line["on"] == "both" and [(p["doc"], p["role"]) for p in line["per"]] == [("s", "source"), ("t", "target")] and line["text"].startswith("사업계획서 — 작성 요령 표 2 —")
    X.start("t", {"from": "map", "to": "clean"})
    rec = _done("t")
    assert rec["status"] == "done", rec["end"]
    assert fake.calls[-2:] == [("cleanup", "s"), ("cleanup", "t")] and fake.fenced[-2:] == [True, True]
    assert rec["stages"][1]["text"] == "사업계획서 — 작성 요령 표 2을(를) 지웠습니다 · 연차보고서 — 작성 요령 표 4을(를) 지웠습니다"
    after = {g["id"]: g for g in X.status_of("t")["stages"]}["clean"]
    assert after["left"] == 0 and next(s for s in after["steps"] if s["key"] == "guide")["text"] == "사업계획서 — 지울 안내가 없습니다 · 지울 안내가 없습니다"


def test_link_reanalyzes_a_source_document_whose_structure_this_definition_changes(fake, monkeypatch):
    """원본 문서에 「프로젝트 구성 반영」 을 놓은 정의 — 자리 연결의 안전망이 원본 문서의 구조 반영 전 스크립트 분석도 다시(2 → 3단계). 그 줄이 없는 정의(붙박이)는 원본 문서를 다시 분석하지 않는다."""
    hrev = {"s": 0, "t": 0}
    facts0, heads0 = fake.facts, fake.start_heads
    fake.facts = lambda doc: (lambda f: (f["heads"].update(rev2=hrev[doc], rev3=hrev[doc], asked=False), f)[1])(facts0(doc))

    def start(doc, how="first"):
        fake.calls.append(("how", doc, how))
        hrev[doc] = 3
        return heads0(doc, how)
    fake.start_heads = start
    fake.divs["s"]["applied"]["rev"] = 3   # 원본 문서의 구조 반영(차례 3)이 그 분석(차례 0) 뒤
    X.start("t", {"from": "map"})
    assert _done("t")["status"] == "done" and not [c for c in fake.calls if c[0] == "how"]   # 붙박이 — 원본 문서는 그대로
    fake2 = FillFake()
    fake2.facts = lambda doc: (lambda f: (f["heads"].update(rev2=hrev[doc], rev3=hrev[doc], asked=False), f)[1])(FillFake.facts(fake2, doc))
    heads2 = fake2.start_heads
    fake2.start_heads = lambda doc, how="first": (fake2.calls.append(("how", doc, how)), hrev.__setitem__(doc, 3), heads2(doc, how))[2]
    fake2.divs["s"]["applied"]["rev"] = 3
    hrev.update(s=0, t=0)
    X.RUNS.clear(); X.BUSY.clear(); X.LAST.clear()
    X.UNIT = fake2
    _on(monkeypatch, division="both")
    X.start("t", {"from": "map"})
    rec = _done("t")
    assert rec["status"] == "done", rec["end"]
    assert [c for c in fake2.calls if c[0] == "how"] == [("how", "s", 2), ("how", "s", 3)]
    assert rec["steps"][0]["text"].startswith("안전망 — 헤딩·표 분석(스크립트) — 사업계획서(구조 반영 뒤 다시) · 연결 목록")
