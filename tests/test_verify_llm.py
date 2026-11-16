"""검증 LLM 검토(spec_hwpx_웹편집 ② §4-1) — 답의 검사(apply) · 마지막 단계(run_flow "*") · 단계 상태 반영 · running/reviewing."""
import json
import threading

from app import verify, verify_llm


def _job(kind="import", **status):
    job = verify.Job(kind, verify.steps(kind))
    for k, *_ in verify.steps(kind):   # 적지 않은 스크립트 단계는 통과로(LLM 검토는 스크립트 단계가 다 끝난 뒤에 돈다)
        if k != "llm":
            job.set(k, "ok", "")
    for k, (st, detail) in status.items():
        job.set(k, st, detail)
    return job


def _steps(**status):
    return [{"key": k, "title": k, "status": st, "detail": d} for k, (st, d) in status.items()]


def test_apply_checks_answer():
    steps = _steps(fonts=("fail", "굵게 다름 3,580자"), letters=("warn", "앞 공백"), pages=("warn", "못 맞춤"), owpml=("warn", "규칙"), map=("ok", ""))
    got, rejected = verify_llm.apply(steps, {"steps": [
        {"key": "fonts", "verdict": "reference", "status": "ok", "reason": "  HCRBatang-Bold 에\n몰림 "},   # 받음 — 실패 → 통과
        {"key": "letters", "verdict": "mixed", "status": "fail", "reason": "x"},     # 스크립트(주의)보다 무거움 → 그대로
        {"key": "pages", "verdict": "reference", "status": "fail", "reason": "x"},   # reference 에 fail 은 둘 수 없음 → 그대로
        {"key": "map", "verdict": "real", "status": "warn", "reason": "x"},          # 대상 아님(통과 단계)
        {"key": "fonts", "verdict": "real", "status": "fail", "reason": "x"},        # 두 번 → 앞의 것만
    ]})
    assert got["fonts"] == {"status": "ok", "llm": {"verdict": "reference", "status": "ok", "reason": "HCRBatang-Bold 에 몰림"}}
    assert got["letters"]["status"] == "warn" and got["pages"]["status"] == "warn"
    assert "map" not in got and "owpml" not in got   # owpml 은 답이 없음 → 반영 안 함
    text = " ".join(rejected)
    assert "「map」" in text and "두 번" in text and "「owpml」 답 없음" in text and "무거운" in text and "기준 쪽 사정 인데 상태 「fail」" in text


def test_apply_unclear_keeps_script_status():
    got, _ = verify_llm.apply(_steps(render=("fail", "다른 쪽 2개")), {"steps": [{"key": "render", "verdict": "unclear", "status": "ok", "reason": "모름"}]})
    assert got["render"]["status"] == "fail" and got["render"]["llm"]["verdict"] == "unclear"


def test_run_flow_star_runs_last_even_when_blocked():
    job = verify.Job("t", [(k, k, "") for k in ("a", "b", "c", "llm")])
    order = []

    def a():
        raise verify.Stop("a 막힘", "fail")

    def last():
        order.append(("llm", {s["key"]: s["status"] for s in job.view()["steps"]}))
        job.set("llm", "ok")
    verify.run_flow(job, {"a": a, "b": lambda: (order.append("b"), job.set("b", "ok")), "c": lambda: job.set("c", "ok"), "llm": last},
                    {"c": ["a"], "llm": "*"})
    seen = order[-1][1]
    assert seen["a"] == "fail" and seen["b"] == "ok" and seen["c"] == "skip"   # 막힌 뒤 단계까지 끝난 뒤에 돎
    assert job.step("llm")["status"] == "ok" and job.finished


def test_review_skips_without_targets(monkeypatch):
    monkeypatch.setenv("NFM_VERIFY_LLM", "on")
    monkeypatch.setattr(verify_llm.llm, "call", lambda *a, **k: (_ for _ in ()).throw(AssertionError("부르면 안 됨")))
    job = _job(package=("ok", ""), fonts=("ok", ""), render=("skip", "PDF 없음"))
    verify_llm.review(job)
    assert job.step("llm")["status"] == "skip" and "주의·실패 단계 없음" in job.step("llm")["detail"]


def test_review_off_keeps_script(monkeypatch):
    job = _job(fonts=("fail", "굵게 다름"))
    verify_llm.review(job)   # conftest 가 NFM_VERIFY_LLM=off
    assert job.step("fonts")["status"] == "fail" and "llm" not in job.step("fonts")
    assert job.step("llm")["status"] == "skip" and "꺼져" in job.step("llm")["detail"]


def test_review_applies_and_keeps_script(monkeypatch):
    monkeypatch.setenv("NFM_VERIFY_LLM", "on")
    monkeypatch.setattr(verify_llm.llm, "status", lambda: {"available": True})
    sent = {}
    gate = threading.Event()

    def call(schema, content, what, **kw):
        sent.update(content=content, what=what, kw=kw)
        gate.wait(5)
        return {"data": {"steps": [{"key": "fonts", "verdict": "reference", "status": "ok", "reason": "함초롬바탕 글자가 모두 HCRBatang-Bold 로 찍힘"},
                                   {"key": "letters", "verdict": "real", "status": "warn", "reason": "앞 공백이 다름"}], "summary": "글꼴은 PDF 쪽 사정"},
                "backend": "cli", "model": "claude-fable-5-2", "effort": "medium", "ms": 4200, "costUsd": None, "error": None}
    monkeypatch.setattr(verify_llm.llm, "call", call)
    job = _job(package=("ok", "일치"), pdf=("skip", "한글 없음"), fonts=("fail", "굵게 다름 3,580자"), letters=("warn", "앞 공백 칸 수 3/5"))
    job.set("fonts", "fail", "굵게 다름 3,580자", fonts={"faces": [{"web": "함초롬바탕", "pdf": {"HCRBatang-Bold": 3355}, "bold": {"보통→굵게": 3322, "굵게→굵게": 33}}]},
            unjudged=["Type3 글꼴 글자 30자 — PDF 로 굵게를 알 수 없음"])
    t = threading.Thread(target=verify_llm.review, args=(job,))
    t.start()
    for _ in range(200):
        if job.step("llm")["status"] == "run":
            break
        threading.Event().wait(0.01)
    v = job.view()
    assert v["reviewing"] and not v["running"] and v["status"] == "fail"   # LLM 이 도는 동안: 스크립트 판정 · 「진행 중」 아님
    gate.set()
    t.join(5)
    assert sent["what"] == "verify-llm-import" and sent["kw"]["effort"] == "medium"
    c = sent["content"]
    data = json.loads(c.rsplit("## 자료(JSON)\n", 1)[1])
    assert data["targets"] == ["letters", "fonts"] and data["kind"] == "import"
    fonts = next(s for s in data["steps"] if s["key"] == "fonts")
    face = fonts["data"]["fonts"]["faces"][0]   # 글꼴 판정 줄의 PDF 글꼴 · 굵게 짝이 줄이지 않고 그대로(깊이 5)
    assert face["pdf"] == {"HCRBatang-Bold": 3355} and face["bold"] == {"보통→굵게": 3322, "굵게→굵게": 33}
    assert fonts["unjudged"] == ["Type3 글꼴 글자 30자 — PDF 로 굵게를 알 수 없음"]
    assert next(s for s in data["steps"] if s["key"] == "pdf")["unjudged"] == ["이 단계를 건너뜀 — 한글 없음"]
    assert "## 판단 지침 — 검증 LLM 검토" in c and "HCRBatang-Bold" in c.rsplit("## 자료(JSON)\n", 1)[0]   # 판단 지침(merge_guides_default/verify.md)이 붙음
    f = job.step("fonts")
    assert f["status"] == "ok" and f["script"] == {"status": "fail", "detail": "굵게 다름 3,580자"} and f["llm"]["verdict"] == "reference"
    assert job.step("letters")["status"] == "warn" and job.step("letters")["llm"]["verdict"] == "real"
    llm_step = job.step("llm")
    assert llm_step["status"] == "ok" and "기준 쪽 사정 1" in llm_step["detail"] and "실제 문제 1" in llm_step["detail"] and llm_step["review"]["guide"]["name"] == "verify"
    v = job.view()
    assert not v["reviewing"] and v["status"] == "warn"   # 반영한 상태로 — 글꼴은 통과, 레터는 주의


def test_review_llm_error_keeps_script(monkeypatch):
    monkeypatch.setenv("NFM_VERIFY_LLM", "on")
    monkeypatch.setattr(verify_llm.llm, "status", lambda: {"available": True})
    monkeypatch.setattr(verify_llm.llm, "call", lambda *a, **k: {"data": None, "error": "cli: exit 1", "ms": 10})
    job = _job("edit", epages=("fail", "예상 밖 차이 3"))
    verify_llm.review(job)
    assert job.step("epages")["status"] == "fail" and job.step("llm")["status"] == "skip" and "cli: exit 1" in job.step("llm")["detail"]


def test_steps_and_deps_have_llm_last():
    for kind, deps in (("import", verify.IMPORT_DEPS), ("edit", verify.EDIT_DEPS)):
        assert verify.steps(kind)[-1][0] == "llm" and deps["llm"] == "*"
    assert verify.steps("import", "docx")[-1][1] == "LLM 검토"


def test_fonts_unjudged():
    r = {"chars": 100, "bold": {"checked": 70}, "faces": [{"web": "한양견고딕", "chars": 30, "verdict": "hangul"}], "latin": [{"web": "Arial", "chars": 5, "verdict": "same"}]}
    out = verify.fonts_unjudged(r)
    assert "Type3 글꼴 글자 30자" in out[0] and "한양견고딕(30자)" in out[1]


def test_small_trims_lists_and_text():
    s = verify_llm._small({"a": list(range(30)), "t": "가" * 500})
    assert s["a"][-1] == "… 모두 30개" and len(s["a"]) == verify_llm.LIST_MAX + 1 and len(s["t"]) == verify_llm.TEXT_MAX
