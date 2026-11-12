"""할 일 프롬프트(spec_작업 ② §13) — app/job_prompts.py · 자리 연결 LLM 검토 프롬프트에 붙는지 · 저장소 jobs/plan_to_report.md 의 전제. LLM 은 부르지 않는다."""
from app import job_prompts as J
from app import merge_llm as L

PAYLOAD = {"targets": [], "sources": [], "examples": [], "left": 0}


def test_get_body_part(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_JOBS", str(tmp_path))
    assert J.get("plan_to_report") is None and J.part(None) == "" and J.brief(None) is None   # 파일 없음 — 프롬프트는 전과 같다
    (tmp_path / "plan_to_report.md").write_text("# 할 일 프롬프트 — 시험 이관\n\n<!-- 사람만 보는 메모 -->\n\n## 기준\n- 기준은 계획서\n", encoding="utf-8")
    p = J.get("plan_to_report")
    assert (p["job"], p["name"]) == ("plan_to_report", "시험 이관") and len(p["sha1"]) == 40
    assert J.body(p["text"]) == "## 기준\n- 기준은 계획서"   # 제목 줄·주석은 안 보낸다
    part = J.part(p)
    assert part.startswith("\n\n## 할 일 — 시험 이관") and "기준은 계획서" in part and "사람만 보는 메모" not in part
    assert J.brief(p) == {"job": "plan_to_report", "name": "시험 이관", "sha1": p["sha1"]}
    assert J.get("../plan_to_report") is None and J.get("") is None and J.get(None) is None   # 키 꼴이 아니면 읽지 않는다
    (tmp_path / "plan_fit.md").write_text("# 제목뿐\n<!-- 메모 -->\n", encoding="utf-8")
    assert J.get("plan_fit") and J.part(J.get("plan_fit")) == "" and J.brief(J.get("plan_fit")) is None   # 보낼 글이 없는 파일
    monkeypatch.setenv("NFM_JOBS", "off")
    assert J.jobs_dir() is None and J.get("plan_to_report") is None


def test_merge_prompt_carries_the_job_prompt_of_the_work(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_JOBS", str(tmp_path))
    (tmp_path / "plan_to_report.md").write_text("# 할 일 프롬프트 — 시험 이관\n\n- 기준은 계획서\n", encoding="utf-8")
    monkeypatch.setattr(J.works, "work", lambda wid: {"task": {"job": "plan_to_report"}} if wid == "w1" else {"task": None} if wid == "w2" else None)
    job = J.for_work("w1")
    assert job["job"] == "plan_to_report" and J.for_work("w2") is None and J.for_work("없음") is None   # 할 일을 안 고른 작업 · 없는 작업
    plain, _ = L.prompt(PAYLOAD)
    text, forms = L.prompt(PAYLOAD, job=job)
    assert "## 할 일" not in plain and forms == []
    assert text.startswith(L.CONTRACT) and text.index("## 할 일 — 시험 이관") < text.index("## 자료(JSON)") and "기준은 계획서" in text   # 계약 뒤 · 자료 앞
    assert text.replace(J.part(job), "") == plain   # 그 절 말고는 그대로
    seen = []
    r = L.ask(PAYLOAD, call=lambda schema, content, what, **kw: seen.append(content) or {"data": None}, job=job)
    assert r["job"] == J.brief(job) and "기준은 계획서" in seen[0]
    assert L.ask(PAYLOAD, call=lambda *a, **kw: {"data": None})["job"] is None


def test_repo_plan_to_report_prompt_says_the_plan_is_the_basis(monkeypatch):
    monkeypatch.delenv("NFM_JOBS")   # 저장소의 jobs/ 를 본다
    p = J.get("plan_to_report")
    assert p and p["name"] == "사업계획서 → 연차보고서 이관"
    b = J.body(p["text"])
    assert "연차보고서에 필요한 내용을 추출" in b and "기준은 연구개발계획서" in b and "연차보고서(빈 서식)에서 값을 가져오지 않는다" in b
    assert "사용자 원문" not in b and not b.startswith("#  ") and "할 일 프롬프트 —" not in b   # 주석(원문 기록)·제목 줄은 프롬프트에 안 들어간다
