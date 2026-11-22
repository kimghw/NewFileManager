"""조립한 TASK(spec_워크플로우 ② §14 · app/custom_tasks.py · API /api/tasks) — 화면에서 단계를 골라 만든 TASK: 저장 · 검사 · 서버가 그 키를 TASK 로 받음 · 등록부에 조립돼 섬 · 전제 · 원본/목적 문서 ·
문서마다 단위문서 TASK(② §15 — 원본 · 목적 문서마다 고른 단계 assign + llm · 옛 줄 호환(옛 뜻 그대로) · 칸 cells · /api/workflow 의 roles) ·
2차 고침(astra 검토 2026-11-19): 허용되는 배정 전부 · 쓰는 중인 정의(409 · 「복제」) · 저장 파일 보호(깨진 JSON · 꼴이 틀린 줄)."""
import itertools
import json
import re

import pytest
from fastapi.testclient import TestClient

from app import custom_tasks as C
from app import job_prompts, server, workflow, works


@pytest.fixture
def client():
    yield TestClient(server.app)


def test_stage_ids_follow_the_registry():
    assert C.STAGES == tuple(m[0] for m in workflow.STAGE_MODULES) and set(C.STAGE_GROUP) == set(C.STAGES)   # 일반 단계의 차례 = 등록부의 단계 차례
    assert C.FILES == works.FILE_LABEL and all(a in C.FILES and b in C.FILES and a != b for a, b in C.PAIRS) and C.BASE in workflow.BY_JOB
    assert C.ROLES == tuple(r for r, _ in workflow.ROLES) and C.ROLE_STAGES == {"source": ("stage_review",), "target": C.STAGES}   # 원본 문서는 「문서 검토」 만(② §15)
    assert C.BASE_ROLE == "source" and C.SOURCE_USE == ("stage_fit", "stage_fill")   # 조립한 워크플로우의 구성의 기준 = 원본 · 원본을 쓰는 목적 문서의 단계
    assert C.NO_SOURCE == "원본 문서를 쓰는 단계가 없습니다 — 원본 문서의 「문서 검토」 나 목적 문서의 「구성 맞추기」 · 「내용 넣기」 를 고르세요"
    assert C.IN_USE.format(n=2) == "이 워크플로우로 하던 작업이 2개 있어 단계를 바꿀 수 없습니다 — 「복제」 로 새 워크플로우를 만들어 고치세요"
    assert C.DELETE_IN_USE.format(n=3) == ("이 워크플로우를 쓰는 작업이 3개 있어 지울 수 없습니다 — 지금 워크플로우로 둔 작업은 다른 워크플로우로 바꾸고, "
                                           "대시보드 「이 문서의 워크플로우」 목록에서 빼면 지울 수 있습니다")
    assert [C._eun(w) for w in ("구성 맞추고 넣기", "옛 뜻", "배정 1", "배정 2", "ABC", "")] == ["는", "은", "은", "는", "는", "는"]   # 「…」 뒤 조사 — 끝 글자의 받침
    assert C.BROKEN.format(name="tasks.json") == "저장 파일(tasks.json)을 읽지 못해 쓰지 않습니다 — 파일을 고치거나 옮긴 뒤 다시 하세요" and issubclass(C.Refused, ValueError)
    # llm 규칙 — 「문서 검토」 를 고른 원본 · 「문서 검토」 를 골랐고 「구성 맞추기」 는 안 고른 목적
    rule = lambda s, t: C.llm_rule({"source": s, "target": t})  # noqa: E731
    assert rule(["stage_review"], ["stage_review", "stage_fill"]) == ["source", "target"] and rule(["stage_review"], ["stage_review", "stage_fit"]) == ["source"]
    assert rule([], ["stage_review", "stage_fit"]) == [] and rule([], ["stage_fill"]) == [] and rule([], ["stage_review", "stage_clean", "stage_fill"]) == ["target"]
    assert C.from_stages(["stage_fill", "stage_review"]) == {"source": ["stage_review"], "target": ["stage_review", "stage_fill"], "llm": ["source"]}   # 옛 뜻 — 1단계 LLM 은 원본만
    assert C.from_stages(["stage_fit"]) == {"source": [], "target": ["stage_fit"], "llm": []}


def test_create_validates_and_keeps_the_general_order():
    t = C.create({"name": "  구성만   맞추기 ", "stages": ["stage_fit", "stage_review"], "desc": "프레임까지"}, ["사업계획서 취합"])
    assert C.KEY.fullmatch(t["key"]) and t["name"] == "구성만 맞추기" and t["stages"] == ["stage_review", "stage_fit"] and (t["source"], t["target"]) == ("plan", "report")   # 고른 것만 · 차례는 일반 단계의 차례
    assert C.get(t["key"])["desc"] == "프레임까지" and C.is_key(t["key"]) and not C.is_key("plan_to_report") and not C.is_key("u_zzzzzzzz")
    for body, word in (({"name": "", "stages": ["stage_fit"]}, "이름"), ({"name": "구성만 맞추기", "stages": ["stage_fit"]}, "이미 있는"), ({"name": "사업계획서 취합", "stages": ["stage_fit"]}, "이미 있는"),
                       ({"name": "새", "stages": []}, "하나 이상"), ({"name": "새", "stages": ["nope"]}, "단계"), ({"name": "새", "stages": ["stage_fit"], "source": "plan", "target": "plan"}, "문서 쌍"),
                       ({"name": "x" * 41, "stages": ["stage_fit"]}, "40자"), ({"name": "새", "stages": ["stage_clean"]}, "원본 문서를 쓰는 단계가 없습니다")):   # 옛 꼴도 — 원본 = [] · 목적 = 정리만
        with pytest.raises(ValueError, match=word):
            C.create(body, ["사업계획서 취합"])
    for body, text in (({"name": "구성만 맞추기", "stages": ["stage_fit"]}, "「구성만 맞추기」는 이미 있는 워크플로우 이름입니다"), ({"name": " ", "stages": ["stage_fit"]}, "워크플로우 이름을 적으세요"),
                       ({"name": "x" * 41, "stages": ["stage_fit"]}, "워크플로우 이름은 40자까지입니다")):   # 화면에 그대로 보이는 글 — 전체는 「워크플로우」
        with pytest.raises(ValueError, match="^" + re.escape(text) + "$"):
            C.create(body, ["사업계획서 취합"])
    assert t["assign"] == {"source": ["stage_review"], "target": ["stage_review", "stage_fit"], "llm": ["source"]}   # 옛 꼴 요청 — 옛 줄 규칙(from_stages)
    u = C.update(t["key"], {"stages": ["stage_clean", "stage_fill"], "premise": "실적은 비워 둔다"})
    assert u["stages"] == ["stage_fill", "stage_clean"] and u["name"] == "구성만 맞추기" and u["premise"] == "실적은 비워 둔다" and u["assign"]["llm"] == []
    with pytest.raises(ValueError, match="^문서 쌍은 고칠 수 없습니다 — 새 워크플로우로 만드세요$"):
        C.update(t["key"], {"source": "report"})
    assert C.update("u_00000000", {"name": "없음"}) is None and C.delete(t["key"]) and not C.delete(t["key"]) and C.all() == []


def test_server_takes_the_key_as_a_task_and_knows_its_documents(client):
    t = C.create({"name": "넣기만", "stages": ["stage_fill"]})
    key = t["key"]
    assert works.TARGET_FILE.get(key) == "report" and key in works.TARGET_FILE and works.TARGET_FILE[key] == "report" and "u_00000000" not in works.TARGET_FILE
    assert works.TARGET_FILE == {"plan_to_report": "report", "plan_merge": "plan"}   # 붙박이 사전의 내용은 그대로(조립한 TASK 는 저장소에서 읽는다)
    assert C.source_file(key) == "plan" and C.source_file("plan_to_report") == "plan" and C.target_file("plan_to_report") is None
    d = client.post("/api/docs?new=1", files={"file": ("a.docx", _docx())}).json()["docId"]
    ok = client.put(f"/api/works/{d}/task", json={"kind": "rnd", "file": "report", "job": key, "project": "조립"})
    assert ok.status_code == 200 and ok.json()["task"]["job"] == key
    assert client.put(f"/api/works/{d}/task", json={"kind": "rnd", "file": "report", "job": "u_00000000", "project": "조립"}).status_code == 400   # 저장소에 없는 키
    gone = client.delete(f"/api/tasks/{key}")
    assert gone.status_code == 409 and "1개" in gone.json()["detail"]   # 그 TASK 로 하던 작업이 있으면 못 지운다


def _docx():
    import io

    import docx
    f, d = io.BytesIO(), docx.Document()
    d.add_paragraph("글")
    d.save(f)
    return f.getvalue()


def test_premise_is_the_written_text_or_the_base_tasks(monkeypatch):
    from pathlib import Path
    monkeypatch.setenv("NFM_JOBS", str(Path(__file__).parents[1] / "jobs"))   # 저장소의 jobs/(conftest 는 임시 폴더로 돌려 둔다)
    a, b = C.create({"name": "물려받음", "stages": ["stage_fill"]}), C.create({"name": "제 전제", "stages": ["stage_fill"], "premise": "계획 쪽만 넣는다"})
    base, pa, pb = job_prompts.get(C.BASE), job_prompts.get(a["key"]), job_prompts.get(b["key"])
    line = workflow.picked_line(C.get(a["key"]))   # 물려받은 전제의 맨 앞 한 줄(spec_워크플로우 ② §15) — 고른 단계 · 고르지 않은 단계는 하지 않는다
    assert line == "이 워크플로우는 조립한 것 — 고른 단계: [원본 문서(사업계획서): 없음 / 목적 문서(연차보고서): 「내용 넣기」] · 전제의 단계 설명 가운데 고르지 않은 단계는 하지 않는다."
    assert pa["job"] == a["key"] and "물려받음" in pa["name"] and pa["path"] == base["path"] and pa["text"] != base["text"]   # 비우면 틀이 같은 붙박이 TASK(이관)의 전제 + 그 한 줄
    assert job_prompts.body(pa["text"]) == line + "\n\n" + job_prompts.body(base["text"]) and pa["sha1"] != base["sha1"] and len(pa["sha1"]) == 40   # 제목 · 주석을 뺀 글의 맨 앞 · 보낸 글의 sha1
    assert job_prompts.part(pa).count(line) == 1 and job_prompts.brief(pa) == {"job": a["key"], "name": pa["name"], "sha1": pa["sha1"]}
    assert pb["text"] == "계획 쪽만 넣는다" and pb["name"] == "제 전제" and pb["path"] == "" and "조립한 것" not in pb["text"]   # 적은 전제에는 붙이지 않는다
    assert job_prompts._lead("제목 없는 글", "한 줄") == "제목 없는 글\n\n한 줄\n"   # 첫 줄이 제목이 아니면 끝에(제목 읽기를 흐트리지 않게)


def test_api_lists_creates_edits_and_the_registry_assembles_it(client):
    v = client.get("/api/tasks").json()
    assert v["tasks"] == [] and [s["id"] for s in v["stages"]] == list(C.STAGES) and [s["name"] for s in v["stages"]] == ["문서 검토", "구성 맞추기", "내용 넣기", "문서 정리"]
    assert v["pairs"] == [{"source": "plan", "target": "report", "name": "사업계획서 → 연차보고서"}] and len(v["blocked"]) == 1 and v["base"] == "plan_to_report"   # 취합 · 문서 하나는 shapes 의 soon 으로(② §18-8 「문서 입출력」)
    assert client.post("/api/tasks", json={"name": "취합 옛 꼴", "shape": "gather", "assign": {"source": ["stage_review"], "target": ["stage_fill"]}}).status_code == 400   # 옛 꼴(assign)로 다른 틀을 이관으로 저장하지 않는다
    assert v["warn"] == {"fillNoFit": workflow.FILL_NO_FIT} and workflow.FILL_NO_FIT == "목적 문서에 구조 반영 기록이 있고 두 문서의 프로젝트 구성 값이 같아야 자리 연결이 섭니다(손으로 맞춘 구조는 「반영 전」 으로 멈춤)"
    assert client.put("/api/tasks/u_00000000", json={"name": "x"}).json()["detail"] == "그런 워크플로우가 없습니다" and client.delete("/api/tasks/u_00000000").json()["detail"] == "그런 워크플로우가 없습니다"
    assert client.post("/api/tasks", json={"name": "", "stages": ["stage_fit"]}).status_code == 400
    r = client.post("/api/tasks", json={"name": "구성 맞추고 넣기", "desc": "정리는 안 함", "stages": ["stage_fill", "stage_fit"]})
    t = r.json()["task"]
    assert r.status_code == 201 and t["groups"] == ["frame", "map"] and t["sourceName"] == "사업계획서" and t["targetName"] == "연차보고서"
    L = client.get("/api/workflow").json()
    mine = L["tasks"][-1]
    assert mine["job"] == t["key"] and mine["custom"] and mine["name"] == "구성 맞추고 넣기" and mine["doc"] == "" and mine["prompt"] is None
    assert mine["premiseFrom"] == "plan_to_report" and mine["base"] == "source"   # base = 구성의 기준 문서 역할(② §15) — 전제를 물려받는 붙박이 키는 premiseFrom
    assert [(g["id"], g["no"], g["name"], g["module"]) for g in mine["stages"]] == [("frame", "1단계", "구성 맞추기", "stage_fit"), ("map", "2단계", "내용 넣기", "stage_fill")]   # 고른 단계만 · 번호는 1부터 다시
    assert [s["key"] for s in mine["stages"][0]["steps"]] == ["files", "configLoad", "config", "division", "reheads", "reheadsLlm"]   # 맨 앞 묶음이 「준비」 를 가진다
    used = {c["id"]: c["usedBy"] for c in L["common"]}
    assert used["stage_fit"] == ["plan_to_report", t["key"]] and used["stage_review"] == ["plan_to_report"] and t["key"] in used["division"]
    assert [x["job"] for x in L["tasks"][:-1]] == [x["job"] for x in workflow.TASKS] and t["key"] not in workflow.markdown()   # 붙박이 등록부 · 만든 글(workflow.md)은 그대로
    js = client.get("/api/tasks.js")
    assert js.headers["cache-control"] == "no-store" and "javascript" in js.headers["content-type"] and js.text.startswith('if (typeof taskCatalogCustom === "function") taskCatalogCustom([') and t["key"] in js.text
    assert js.text.endswith(', {"broken": false});\n') and '"inUse"' not in js.text and '"sig"' in js.text and '"descAuto"' in js.text   # 둘째 인자 = 저장 파일을 못 읽었나 · 쓰는 곳은 싣지 않는다
    e = client.put(f"/api/tasks/{t['key']}", json={"name": "넣기까지", "stages": ["stage_review", "stage_fit", "stage_fill"]}).json()["task"]
    assert e["name"] == "넣기까지" and e["groups"] == ["review", "frame", "map"] and client.put("/api/tasks/u_00000000", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/tasks/{t['key']}").json() == {"deleted": True} and client.get("/api/tasks").json()["tasks"] == [] and client.delete(f"/api/tasks/{t['key']}").status_code == 404


def test_assign_picks_steps_per_document_and_still_takes_the_old_form():
    """문서마다 단위문서 TASK(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」 — 2026-11-19 사용자 "목적문서랑 원본문서에 대해서 각각 task 를 할당할 수 있도록 해줘"):
    assign = 원본 · 목적 문서마다 고른 단계(일반 차례 — 원본은 「문서 검토」 만) · stages = 두 역할의 합집합(같이 씀) · 옛 꼴(stages 만)도 받는다(assign 이 먼저)."""
    t = C.create({"name": "문서마다", "assign": {"source": ["stage_review"], "target": ["stage_fill", "stage_review"]}})
    assert t["assign"] == {"source": ["stage_review"], "target": ["stage_review", "stage_fill"], "llm": ["source", "target"]} and t["stages"] == ["stage_review", "stage_fill"]   # llm = 규칙(구성 맞추기 없음 — 목적도)
    assert C.create({"name": "원본만", "assign": {"source": ["stage_review"], "target": []}})["stages"] == ["stage_review"]   # 하나 이상이면 된다(원본만 검토)
    assert C.create({"name": "옛 꼴", "stages": ["stage_fill", "stage_review"]})["assign"] == {"source": ["stage_review"], "target": ["stage_review", "stage_fill"], "llm": ["source"]}   # 옛 뜻(두 문서 분석 + 원본 LLM)
    assert C.create({"name": "옛 꼴 둘", "stages": ["stage_fit"]})["assign"] == {"source": [], "target": ["stage_fit"], "llm": []}
    assert C.create({"name": "둘 다 보냄", "assign": {"source": [], "target": ["stage_fill"]}, "stages": ["stage_clean"]})["stages"] == ["stage_fill"]   # assign 이 먼저(stages 는 옛 꼴 — assign 이 없을 때만)
    sent = C.create({"name": "복제 꼴", "assign": {"source": ["stage_review"], "target": ["stage_review", "stage_fill"], "llm": ["source"]}})   # 만들 때 보낸 llm 은 받는다(「복제」 — 옛 줄의 「원본만」 을 지킴)
    assert sent["assign"]["llm"] == ["source"] and C.create({"name": "넓힘", "assign": {"source": [], "target": ["stage_review", "stage_fit"], "llm": ["target"]}})["assign"]["llm"] == []   # 규칙보다 넓히지 않는다
    for body, word in (({"name": "새", "assign": {"source": ["stage_fit"], "target": ["stage_fit"]}}, C.SOURCE_ONLY),
                       ({"name": "새", "assign": {"source": ["stage_review", "stage_clean"], "target": []}}, C.SOURCE_ONLY),
                       ({"name": "새", "assign": {"source": [], "target": []}}, "단계를 하나 이상 고르세요"), ({"name": "새", "assign": {}}, "단계를 하나 이상 고르세요"),
                       ({"name": "새", "assign": {"source": [], "target": ["nope"]}}, "단계를 고르세요"), ({"name": "새", "assign": ["stage_fit"]}, "단계를 고르세요"),
                       ({"name": "새", "assign": {"source": "stage_review", "target": []}}, "단계를 고르세요"),
                       ({"name": "새", "assign": {"source": [], "target": ["stage_review", "stage_clean"]}}, C.NO_SOURCE),   # 원본 문서를 쓰는 단계가 없음
                       ({"name": "새", "assign": {"source": ["stage_review"], "target": [], "llm": "source"}}, C.BAD_LLM),
                       ({"name": "새", "assign": {"source": ["stage_review"], "target": [], "llm": ["both"]}}, C.BAD_LLM)):
        with pytest.raises(ValueError, match=re.escape(word)):
            C.create(body)
    assert C.SOURCE_ONLY == "원본 문서는 이 워크플로우에서 바뀌지 않아 「문서 검토」 만 고를 수 있습니다"
    u = C.update(t["key"], {"assign": {"source": [], "target": ["stage_fit", "stage_review"], "llm": ["source", "target"]}})   # 원본 · 목적이 바뀜 — 보낸 llm 이 아니라 규칙
    assert u["assign"] == {"source": [], "target": ["stage_review", "stage_fit"], "llm": []} and u["stages"] == ["stage_review", "stage_fit"] and u["name"] == "문서마다"
    assert C.update(t["key"], {"name": "이름만"})["assign"] == u["assign"]   # 단계를 안 보내면 그대로
    o = C.update(t["key"], {"stages": ["stage_clean", "stage_review"]})   # 옛 꼴로 고쳐 합집합이 달라지면 옛 줄 규칙
    assert o["assign"] == {"source": ["stage_review"], "target": ["stage_review", "stage_clean"], "llm": ["source"]} and o["stages"] == ["stage_review", "stage_clean"] and set(o) == set(t)
    got = C.get(t["key"])
    got["assign"]["target"].append("stage_fill")
    got["assign"]["llm"].append("target")
    got["stages"].append("stage_fill")
    assert C.get(t["key"])["assign"] == o["assign"] and C.get(t["key"])["stages"] == ["stage_review", "stage_clean"]   # 사본 — 돌려받은 값을 고쳐도 저장소는 그대로


def test_same_assignment_keeps_the_stored_llm_and_old_screens_do_not_spread_it():
    """ⓒ 원본 · 목적이 저장된 것과 같은 PUT 은 저장된 llm 을 지킨다(보낸 llm 이 달라도) · 옛 화면의 꼴(stages 만)은 합집합이 같으면 저장된 배정 그대로 — 다르면 옛 줄 규칙."""
    t = C.create({"name": "옛 뜻", "assign": {"source": ["stage_review"], "target": ["stage_review", "stage_fill"], "llm": ["source"]}})
    same = {"source": ["stage_review"], "target": ["stage_fill", "stage_review"]}
    assert C.update(t["key"], {"assign": same})["assign"]["llm"] == ["source"]   # llm 없이 같은 배정
    assert C.update(t["key"], {"assign": {**same, "llm": ["source", "target"]}})["assign"]["llm"] == ["source"]   # 다른 llm 을 보내도 — 배정이 같으면 지킨다
    assert C.update(t["key"], {"name": "이름만", "stages": ["stage_fill", "stage_review"]})["assign"] == {"source": ["stage_review"], "target": ["stage_review", "stage_fill"], "llm": ["source"]}
    p = C.create({"name": "목적만 검토", "assign": {"source": [], "target": ["stage_review", "stage_fit", "stage_fill"]}})
    assert C.update(p["key"], {"desc": "옛 화면", "stages": ["stage_review", "stage_fit", "stage_fill"]})["assign"] == p["assign"]   # 합집합이 같다 — 원본의 「문서 검토」 를 되살리지 않는다
    q = C.update(p["key"], {"stages": ["stage_review", "stage_fill"]})   # 합집합이 다르다 — 옛 줄 규칙(원본 = 문서 검토 · llm = 원본)
    assert q["assign"] == {"source": ["stage_review"], "target": ["stage_review", "stage_fill"], "llm": ["source"]}
    # S7 — 배정이 바뀌어도 llm 은 역할마다: 규칙이 보는 입력(목적 = 문서 검토 · 구성 맞추기)이 그대로인 목적 문서는 저장된 결정(1단계 LLM 없음)을 지킨다
    assert C.update(q["key"], {"assign": {"source": ["stage_review"], "target": ["stage_review"]}})["assign"]["llm"] == ["source"]


def test_llm_is_decided_per_role_when_the_assignment_changes():
    """S7 — 배정이 바뀌어도 1단계 「LLM 검증·보완」(유료)은 역할마다 따진다: 규칙이 그 역할을 보는 입력(원본 = 「문서 검토」 · 목적 = 「문서 검토」 · 「구성 맞추기」)이 저장된 것과 같은
    역할은 저장된 결정을 지키고, 입력이 바뀐 역할만 규칙으로 다시 센다(결과는 늘 규칙의 부분)."""
    p = C.path()
    p.parent.mkdir(parents=True, exist_ok=True)
    old = {"key": "u_0000abcd", "name": "옛 줄", "desc": "", "source": "plan", "target": "report", "stages": ["stage_review", "stage_fill"], "premise": "", "at": 1.0}   # 옛 꼴 — llm = 원본만
    p.write_text(json.dumps({"version": 1, "tasks": [old]}, ensure_ascii=False), encoding="utf-8")
    assert C.get("u_0000abcd")["assign"]["llm"] == ["source"]
    u = C.update("u_0000abcd", {"assign": {"source": ["stage_review"], "target": ["stage_review", "stage_fill", "stage_clean"]}})   # 목적에 「문서 정리」 만 더함
    assert u["assign"] == {"source": ["stage_review"], "target": ["stage_review", "stage_fill", "stage_clean"], "llm": ["source"]}   # 목적 문서의 1단계 LLM 이 더해지지 않는다
    v = C.update("u_0000abcd", {"assign": {"source": ["stage_review"], "target": ["stage_review", "stage_fit", "stage_fill"]}})   # 목적의 입력이 바뀜(구성 맞추기) — 목적만 다시 셈(규칙: 없음)
    assert v["assign"]["llm"] == ["source"]
    w = C.update("u_0000abcd", {"assign": {"source": ["stage_review"], "target": ["stage_review", "stage_fill"]}})   # 다시 구성 맞추기를 뺌 — 목적의 입력이 바뀜 → 규칙(목적도)
    assert w["assign"]["llm"] == ["source", "target"]
    x = C.update("u_0000abcd", {"assign": {"source": [], "target": ["stage_review", "stage_fill"], "llm": ["source", "target"]}})   # 원본을 뺌 — 원본은 규칙(없음) · 목적은 저장된 결정(있음) · 보낸 llm 은 쓰지 않는다
    assert x["assign"]["llm"] == ["target"] and set(x["assign"]["llm"]) <= set(C.llm_rule(x["assign"])) and C.get("u_0000abcd")["assign"] == x["assign"]


_ROLE_SETS = [list(c) for n in range(5) for c in itertools.combinations(C.STAGES, n)]   # 목적 문서가 고를 수 있는 것 — 넷의 부분집합(일반 차례)


def test_every_allowed_assignment_builds_a_workflow_that_matches_it(client):
    """ⓐ 허용되는 배정 전부(원본 [] · [문서 검토] × 목적 넷의 부분집합 — 원본 문서를 쓰는 단계가 없는 것은 400): 등록부(assemble)가 서고 · 단계 key 가 겹치지 않고 ·
    1단계의 「LLM 검증·보완」 은 llm 이 빌 때만 없고 · on · onText 가 계약대로이고 · 묶음 설명(does)과 산출물(output)이 배정과 맞는 낱말을 담는다(GET /api/tasks 의 does 도 같은 글)."""
    made = 0
    for src in ([], ["stage_review"]):
        for dst in _ROLE_SETS:
            r = client.post("/api/tasks", json={"name": f"배정 {made}", "assign": {"source": src, "target": dst}})
            uses = bool(src) or any(s in dst for s in C.SOURCE_USE)
            if not (src or dst) or not uses:
                assert r.status_code == 400 and r.json()["detail"] == ("단계를 하나 이상 고르세요" if not (src or dst) else C.NO_SOURCE), (src, dst)
                continue
            assert r.status_code == 201, (src, dst, r.text)
            made += 1
            v = r.json()["task"]
            A, fit, review = v["assign"], "stage_fit" in dst, bool(src) or "stage_review" in dst
            assert A["llm"] == C.llm_rule(A) and A["source"] == src and A["target"] == dst, (src, dst)
            t = workflow.assemble(C.get(v["key"]))
            groups = {g["id"]: g for g in t["stages"]}
            keys = [s["key"] for g in t["stages"] for s in g["steps"]]
            assert len(keys) == len(set(keys)) and list(groups) == v["groups"] and v["does"] == {g["id"]: g["does"] for g in t["stages"]}, (src, dst)
            assert t["stages"][0]["steps"][0]["key"] == "files" and t["premise_from"] == "plan_to_report", (src, dst)   # 맨 앞 묶음이 「준비」
            assert t["base"] == ("source" if fit else None), (src, dst)   # C8 — 구성의 기준은 목적 문서에 「구성 맞추기」 가 있을 때만(없으면 어디서도 적지 않는다)
            assert re.fullmatch(r"[0-9a-f]{10}", v["sig"]) and v["sig"] == C.sig(C.get(v["key"])), (src, dst)
            assert v["descAuto"] == workflow.custom_desc(C.get(v["key"])) == t["desc"] and ("옮깁니다" in v["descAuto"]) == ("stage_fill" in dst), (src, dst, v["descAuto"])   # T2 — 「내용 넣기」 가 없으면 「옮깁니다」 라 하지 않는다
            assert v["inUse"] == v["listed"] == 0 and v["editWhy"] is None and v["deleteWhy"] is None and v["uses"] == [] and v["usesMore"] == 0, (src, dst)
            # T8 — 시작 점검은 붙박이 이관의 것을 이 조립의 묶음 번호로(없는 묶음의 일만 보는 항목은 빼고 · 없는 번호를 가리키지 않는다)
            nos, ent = {g["no"] for g in t["stages"]}, {c["key"]: c for c in t["entry"]}
            assert {c["when"] for c in t["entry"]} == {"start", "upload", "enter", "manual"} and len(ent) == len(t["entry"]), (src, dst)
            assert all(f"{d}단계" in nos for c in t["entry"] for k in ("does", "miss") for m in re.finditer(r"(\d(?: · \d)*)단계", c[k]) for d in m.group(1).split(" · ")), (src, dst)
            assert ("cond" in ent) == ("links" in ent) == ("kept" in ent) == ("stage_fill" in dst) and ("config" in ent) == ("reheads" in ent) == fit and ("cleanup" in ent) == ("stage_clean" in dst), (src, dst)
            assert ("llmOk" in ent) == (bool(A["llm"]) or fit) and all(len(c[k]) <= 320 for c in t["entry"] for k in ("does", "miss")), (src, dst)
            if "cond" in ent:   # F6 — 「이관 조건」 의 워크플로우 전체 조각 = 흐름 줄과 같은 머리 · 같은 꼬리(구성 맞추기가 있을 때만) · 조립한 워크플로우의 글(task_markdown)에도 같은 글
                cond, base = ent["cond"]["does"], next((r for r in t["roles"] if r["role"] == t["base"]), None)
                assert (f"{workflow.FLOW_HEAD}: 프로젝트 구성 추출 — 구성의 기준: 원본 문서(사업계획서)" in cond) == fit == (base is not None) and "(한 번)" not in cond, (src, dst, cond)
                assert not fit or f"{workflow.FLOW_HEAD}: 프로젝트 구성 추출{workflow.base_text(base)}" in cond, (src, dst)
                assert cond in workflow.task_markdown(v["key"]), (src, dst)
            assert "`" not in t["note"] and "조립" not in t["note"] and "전제" not in t["note"], (src, dst)   # T9 — 화면에 그대로 보이는 글 · 같은 절의 「조립」 · 「전제」 줄과 겹치지 않게
            assert all(len(s[k]) <= 320 for g in t["stages"] for s in g["steps"] for k in ("does", "need", "done", "stop", "left")), (src, dst)   # 한두 줄(등록부의 규칙 그대로)
            on = {s["key"]: s["on"] for g in t["stages"] for s in g["steps"]}
            assert on["files"] == "flow" and all(on[k] == "flow" for k in ("configLoad", "config") if k in on) and all(on[k] == "target" for k in ("division", "reheads", "reheadsLlm", "guide") if k in on)
            assert all(on[k] == "pair" for g in t["stages"] if g["id"] == "map" for k in (s["key"] for s in g["steps"]) if k != "files"), (src, dst)   # 맨 앞 묶음이면 「준비」 가 앞에
            heads = [r for r in C.ROLES if "stage_review" in A[r]]
            assert ("heads" in on) == bool(heads) and ("headsLlm" in on) == bool(A["llm"]), (src, dst)   # LLM 검증·보완은 llm 이 빌 때만 없다
            if heads:
                assert on["heads"] == ("both" if len(heads) == 2 else heads[0])
            if A["llm"]:
                assert on["headsLlm"] == ("both" if len(A["llm"]) == 2 else A["llm"][0])
            L = next(x for x in client.get("/api/workflow").json()["tasks"] if x["job"] == v["key"])
            text = {s["key"]: s["onText"] for g in L["stages"] for s in g["steps"]}
            want = {"flow": "워크플로우 전체 — 문서마다가 아니라 한 번", "source": "원본 문서 — 사업계획서", "target": "목적 문서 — 연차보고서", "both": "두 문서 — 사업계획서 · 연차보고서", "pair": "원본 → 목적 — 사업계획서 → 연차보고서"}
            assert text == {k: want[o] for k, o in on.items()}, (src, dst)
            assert L["flow"][0] == {"stage": t["stages"][0]["id"], "steps": ["files"] + (["configLoad", "config"] if t["stages"][0]["id"] == "frame" else [])} and L["base"] == t["base"]
            assert ("구성의 기준" in workflow.task_markdown(v["key"]).split("## 시작 점검", 1)[0]) == fit, (src, dst)   # base 가 없으면 「구성의 기준」 을 적지 않는다
            d = {g: x["does"] for g, x in groups.items()}
            if "review" in d:
                assert ("LLM" in d["review"]) == bool(A["llm"]) and ("작성 지침" in d["review"]) == ("target" in heads) and "문서는 안 바뀜" in d["review"], (src, dst, d["review"])
                assert d["review"].startswith("두 문서(사업계획서 · 연차보고서)의 헤딩 · 표 분석" if len(heads) == 2 else f"{'원본 문서(사업계획서)' if heads == ['source'] else '목적 문서(연차보고서)'}의 헤딩 · 표 분석"), (src, dst)
                assert all(f"{w}의 LLM 검증·보완" in d["review"] for w in (["두 문서"] if len(A["llm"]) == 2 else ["원본 문서(사업계획서)"] if A["llm"] == ["source"] else ["목적 문서(연차보고서)"] if A["llm"] else [])), (src, dst)
            if "map" in d:   # T4 — 「구성 맞추기」 가 없으면 자리 연결이 서는 조건(FILL_NO_FIT — 조립 화면의 경고와 같은 글)
                assert ("앞의 두 단계(문서 검토 · 구성 맞추기)" in d["map"]) == (fit and review) and (workflow.FILL_NO_FIT in d["map"]) == (not fit), (src, dst, d["map"])
            if "clean" in d:
                assert ("「헤딩 · 표 분석」 줄" in d["clean"]) == review, (src, dst)
                guide = next(s for s in groups["clean"]["steps"] if s["key"] == "guide")
                assert ("「헤딩 · 표 분석」 줄" in guide["left"]) == review, (src, dst)   # 그 줄이 없는 워크플로우에서는 가리키지 않는다
                assert ("④" in guide["need"] + guide["done"]) == ("stage_fill" in dst), (src, dst)   # T1 — 「내용 넣기」 가 없으면 「④ 내용 반영」 을 적지 않는다(화면 셈과 같은 뜻)
            if "map" in groups:
                link = next(s for s in groups["map"]["steps"] if s["key"] == "link")
                assert ("「구성 맞추기」 로 구조를 맞춘" in link["need"]) == fit and (workflow.FILL_NO_FIT in link["need"]) == (not fit), (src, dst)
            out = t["output"]
            if "stage_fill" in dst:
                assert out.startswith("원본(사업계획서)의 내용이 들어간 연차보고서") and ("구조를 프로젝트 구성에 맞춤" in out) == fit, (src, dst, out)
            elif fit:
                assert out.startswith("구조를 프로젝트 구성에 맞춘 연차보고서"), (src, dst, out)
            elif "stage_clean" in dst:
                assert out.startswith("양식 안내(작성요령)를 지운 연차보고서"), (src, dst, out)
            else:
                assert out == ("헤딩 · 표를 분석 · 검증한 사업계획서(문서는 안 바뀜)" if heads == ["source"] else "헤딩 · 표를 분석 · 검증한 두 문서(사업계획서 · 연차보고서 — 문서는 안 바뀜)"), (src, dst, out)
            assert ("양식 안내(작성요령)를 지" in out) == ("stage_clean" in dst) and "TASK" not in out and "TASK" not in " ".join(d.values()), (src, dst)   # 새로 짓는 글은 「워크플로우」(화면 말)
            client.delete(f"/api/tasks/{v['key']}")   # 50개 한도 안에서 돈다
    assert made == 28   # 2 × 16 − 아무것도 안 고름 1 − 원본을 쓰는 단계가 없음 3(목적 = 검토 · 정리 · 검토 + 정리)


def test_old_lines_without_assign_are_read_and_kept(client):
    """옛 줄(assign 없이 stages 만 — ② §14 의 꼴)은 버리지 않고 읽는다: 원본 = 「문서 검토」 가 있으면 [문서 검토] · 목적 = stages · llm = 「문서 검토」 가 있으면 [원본].
    ⓑ 옛 뜻 그대로(astra P1 ⓐ) — 「구성 맞추기」 가 없는 옛 줄도 1단계의 LLM 검증·보완은 원본 문서만(목적 문서의 LLM 을 더하지 않는다 — 유료 대상이 늘지 않음).
    llm 이 없는 새 꼴(첫 판의 줄)은 규칙(llm_rule). 다른 줄을 쓸 때 옛 줄은 읽은 그대로 남는다(고친 줄만 새 꼴로)."""
    p = C.path()
    old = [{"key": "u_0000aaaa", "name": "옛 TASK", "desc": "전의 꼴", "source": "plan", "target": "report", "stages": ["stage_fill", "stage_review", "stage_fit"], "premise": "", "at": 1.0},
           {"key": "u_0000bbbb", "name": "옛 TASK 둘", "desc": "", "source": "plan", "target": "report", "stages": ["stage_fit", "stage_fill"], "premise": "계획 쪽만", "at": 2.0},
           {"key": "u_0000cccc", "name": "옛 TASK 셋", "desc": "", "source": "plan", "target": "report", "stages": ["stage_review", "stage_fill"], "premise": "", "at": 3.0},
           {"key": "u_0000dddd", "name": "새 꼴", "desc": "", "source": "plan", "target": "report", "assign": {"source": ["stage_review", "stage_fit"], "target": ["stage_clean"]}, "stages": ["stage_fill"],
            "premise": "", "at": 4.0}]   # 새 꼴 — assign 이 먼저(원본의 문서 검토 밖 단계는 버리고 stages 는 다시 셈)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": 3, "tasks": old}, ensure_ascii=False), encoding="utf-8")
    assert [(t["key"], t["assign"], t["stages"]) for t in C.all()] == [
        ("u_0000aaaa", {"source": ["stage_review"], "target": ["stage_review", "stage_fit", "stage_fill"], "llm": ["source"]}, ["stage_review", "stage_fit", "stage_fill"]),
        ("u_0000bbbb", {"source": [], "target": ["stage_fit", "stage_fill"], "llm": []}, ["stage_fit", "stage_fill"]),
        ("u_0000cccc", {"source": ["stage_review"], "target": ["stage_review", "stage_fill"], "llm": ["source"]}, ["stage_review", "stage_fill"]),   # ⓑ 옛 뜻 — 원본만
        ("u_0000dddd", {"source": ["stage_review"], "target": ["stage_clean"], "llm": ["source"]}, ["stage_review", "stage_clean"])]   # llm 이 없는 새 꼴 — 규칙
    mine = {t["job"]: t for t in workflow.custom()}
    relay = next(g for g in workflow.BY_JOB["plan_to_report"]["stages"] if g["id"] == "review")
    assert [(s["key"], s["on"], s["does"]) for s in mine["u_0000aaaa"]["stages"][0]["steps"]] == [(s["key"], s["on"], s["does"]) for s in relay["steps"]]   # 전의 동작 = 붙박이 이관의 문서 검토(글까지)
    assert [g["id"] for g in mine["u_0000aaaa"]["stages"]] == ["review", "frame", "map"] and [g["id"] for g in mine["u_0000bbbb"]["stages"]] == ["frame", "map"]
    old3 = mine["u_0000cccc"]["stages"][0]["steps"]
    assert [(s["key"], s["on"]) for s in old3] == [("files", "flow"), ("heads", "both"), ("headsLlm", "source")]   # ⓑ 구성 맞추기가 없는 옛 줄도 1단계 LLM 은 원본만(전과 같다)
    assert "연차보고서는 헤딩 · 표 분석(스크립트)만 합니다" in old3[2]["does"] and "다시 문서 검토(LLM)" not in old3[2]["does"]   # 없는 「다시 문서 검토(LLM)」 를 가리키지 않는다
    v = client.get("/api/tasks").json()["tasks"]
    assert [t["key"] for t in v] == ["u_0000aaaa", "u_0000bbbb", "u_0000cccc", "u_0000dddd"] and v[0]["assign"]["source"] == ["stage_review"] and v[0]["groups"] == ["review", "frame", "map"]
    assert v[3]["groups"] == ["review", "clean"] and v[2]["assign"]["llm"] == ["source"]
    C.create({"name": "새 것", "assign": {"source": [], "target": ["stage_fill"]}})   # 저장소를 다시 쓴다 — 옛 줄은 읽은 그대로(새 꼴로 바꾸지 않는다)
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["version"] == 4 and saved["tasks"][:4] == old and len(saved["tasks"]) == 5
    C.update("u_0000cccc", {"name": "옛 TASK 셋 — 이름만"})   # S8 — 고친 칸만: 배정이 그대로라 옛 꼴(assign 없음) 그대로 · 옛 뜻(llm 원본만)도 그대로
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["tasks"][2] == {**old[2], "name": "옛 TASK 셋 — 이름만"} and "assign" not in saved["tasks"][2]
    assert [saved["tasks"][i] for i in (0, 1, 3)] == [old[0], old[1], old[3]] and C.get("u_0000cccc")["assign"]["llm"] == ["source"]
    C.update("u_0000cccc", {"assign": {"source": ["stage_review"], "target": ["stage_review", "stage_fill", "stage_clean"]}})   # 배정을 바꾸면 그때 새 꼴로(옛 뜻 — 원본만 — 은 역할마다 지킨다: S7)
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["tasks"][2]["assign"] == {"source": ["stage_review"], "target": ["stage_review", "stage_fill", "stage_clean"], "llm": ["source"]} and saved["tasks"][2]["stages"] == ["stage_review", "stage_fill", "stage_clean"]


def test_api_view_has_assign_and_cells_and_the_registry_builds_unit_tasks(client):
    """GET /api/tasks 의 단계마다 문서 역할의 칸(cells — pick · follow · no) · 조립한 TASK 의 assign · /api/workflow 의 roles(단위문서 TASK) · 「LLM 검증·보완」 이 서는 때(② §15)."""
    v = client.get("/api/tasks").json()
    cells = {s["id"]: s["cells"] for s in v["stages"]}
    assert {k: (c["source"]["mode"], c["target"]["mode"]) for k, c in cells.items()} == {"stage_review": ("pick", "pick"), "stage_fit": ("follow", "pick"), "stage_fill": ("follow", "pick"), "stage_clean": ("no", "pick")}
    assert cells["stage_review"]["source"]["text"] == "헤딩 · 표 분석 › LLM 검증·보완" and "「구성 맞추기」 를 고르면" in cells["stage_review"]["target"]["text"] and "「다시 문서 검토(LLM)」" in cells["stage_review"]["target"]["text"]
    assert cells["stage_fit"]["source"]["text"] == "구성의 기준 — 구성 불러오기 › 프로젝트 구성 추출(문서는 안 바뀜)" and cells["stage_fill"]["source"]["text"] == "내용을 줌(바뀌지 않음)"   # 단계 사이 「 › 」(F7)
    assert "← 원본 문서" in cells["stage_fill"]["target"]["text"] and cells["stage_clean"]["source"]["text"] == "원본은 바꾸지 않습니다" and all(c[r]["text"] for c in cells.values() for r in C.ROLES)
    bad = client.post("/api/tasks", json={"name": "x", "assign": {"source": ["stage_clean"], "target": ["stage_clean"]}})
    assert bad.status_code == 400 and bad.json()["detail"] == C.SOURCE_ONLY
    assert client.post("/api/tasks", json={"name": "x", "assign": {"source": [], "target": []}}).json()["detail"] == "단계를 하나 이상 고르세요"
    a = client.post("/api/tasks", json={"name": "목적만 구성까지", "assign": {"source": [], "target": ["stage_fit", "stage_review"]}}).json()["task"]
    b = client.post("/api/tasks", json={"name": "목적만 검토", "assign": {"source": [], "target": ["stage_review", "stage_fill"]}}).json()["task"]
    c = client.post("/api/tasks", json={"name": "두 문서 검토", "assign": {"source": ["stage_review"], "target": ["stage_review", "stage_fit", "stage_fill"]}}).json()["task"]
    assert set(a) == {"key", "name", "desc", "source", "target", "assign", "stages", "premise", "at", "sourceName", "targetName", "groups", "does",
                      "sig", "descAuto", "inUse", "listed", "editWhy", "deleteWhy", "uses", "usesMore", "flow", "shape", "v"}   # C1 — 단계의 지문 · 지은 한 줄 설명 · 쓰는 곳(POST · PUT 의 응답에도 — D1 그 작업들) · 줄 목록(옛 꼴도 — 조립 화면이 줄로 연다: 정의 v2)
    assert a["uses"] == [] and a["usesMore"] == 0   # 새 정의 — 쓰는 작업이 없다
    assert a["assign"] == {"source": [], "target": ["stage_review", "stage_fit"], "llm": []} and a["stages"] == ["stage_review", "stage_fit"] and a["groups"] == ["review", "frame"]
    assert a["does"] == {g["id"]: g["does"] for g in workflow.assemble(C.get(a["key"]))["stages"]} and "LLM" not in a["does"]["review"]   # 묶음 설명 = 등록부의 글(LLM 이 없는 1단계)
    listed = {t["key"]: t for t in client.get("/api/tasks").json()["tasks"]}
    assert listed[a["key"]]["assign"] == a["assign"] and listed[a["key"]]["inUse"] == 0 and set(listed[a["key"]]) == set(a) and listed[a["key"]]["does"] == a["does"]
    js = client.get("/api/tasks.js").text
    assert '"assign": {"source": [], "target": ["stage_review", "stage_fit"], "llm": []}' in js and json.dumps(a["does"]["frame"], ensure_ascii=False) in js   # 화면이 스크립트로 읽는 꼴(view)에도 든다
    L = {t["job"]: t for t in client.get("/api/workflow").json()["tasks"]}
    on = lambda key, gid: [(s["key"], s["on"]) for g in L[key]["stages"] if g["id"] == gid for s in g["steps"]]  # noqa: E731
    assert on(a["key"], "review") == [("files", "flow"), ("heads", "target")]   # 원본은 검토를 안 고름 · 목적은 「구성 맞추기」 를 골라 LLM 은 「다시 문서 검토(LLM)」 에서 — 「LLM 검증·보완」 이 서지 않는다
    assert on(b["key"], "review") == [("files", "flow"), ("heads", "target"), ("headsLlm", "target")]   # 목적만 검토 · 구성 맞추기 없음 — LLM 검증·보완은 목적 문서가 여기서
    assert on(c["key"], "review") == [("files", "flow"), ("heads", "both"), ("headsLlm", "source")]   # 붙박이 이관과 같다
    assert all(s["on"] in workflow.ON for k in (a["key"], b["key"], c["key"]) for g in L[k]["stages"] for s in g["steps"])   # 문서 여럿인 워크플로우 — 모든 단계에 하는 문서
    assert L[a["key"]]["roles"] == [   # 워크플로우 전체(준비 · 구성 불러오기 · 확정)는 어느 문서의 단위문서 TASK 에도 안 든다 — flow
        {"role": "source", "name": "사업계획서", "title": "원본 문서", "kind": "plan", "many": False, "unit": []},
        {"role": "target", "name": "연차보고서", "title": "목적 문서", "kind": "report", "many": False, "unit": [{"stage": "review", "steps": ["heads"]}, {"stage": "frame", "steps": ["division", "reheads", "reheadsLlm"]}]}]
    assert L[a["key"]]["flow"] == [{"stage": "review", "steps": ["files"]}, {"stage": "frame", "steps": ["configLoad", "config"]}] and L[a["key"]]["base"] == "source"
    assert L[c["key"]]["roles"][1]["unit"][-1] == {"stage": "map", "steps": ["link", "llm", "plan", "gaps", "tableMap", "apply", "later"]}
    assert L[c["key"]]["output"] == "원본(사업계획서)의 내용이 들어간 연차보고서 초안(구조를 프로젝트 구성에 맞춤)" and L[a["key"]]["output"] == "구조를 프로젝트 구성에 맞춘 연차보고서"   # 실제로 바뀌는 것
    e = client.put(f"/api/tasks/{b['key']}", json={"assign": {"source": ["stage_review"], "target": ["stage_review"]}}).json()["task"]
    assert e["stages"] == ["stage_review"] and e["groups"] == ["review"] and e["assign"] == {"source": ["stage_review"], "target": ["stage_review"], "llm": ["source", "target"]}
    L2 = {t["job"]: t for t in client.get("/api/workflow").json()["tasks"]}
    assert [(s["key"], s["on"]) for s in L2[b["key"]]["stages"][0]["steps"]] == [("files", "flow"), ("heads", "both"), ("headsLlm", "both")]   # 두 문서 다 검토 · 구성 맞추기 없음 — LLM 도 두 문서
    assert L2[b["key"]]["output"] == "헤딩 · 표를 분석 · 검증한 두 문서(사업계획서 · 연차보고서 — 문서는 안 바뀜)"
    assert client.put(f"/api/tasks/{b['key']}", json={"assign": {"source": ["stage_fit"], "target": ["stage_fit"]}}).json()["detail"] == C.SOURCE_ONLY
    assert client.put(f"/api/tasks/{b['key']}", json={"assign": {"source": [], "target": ["stage_review"]}}).json()["detail"] == C.NO_SOURCE   # 원본을 쓰는 단계가 없음(400)


def _work_with(client, job):
    """docx 작업 하나를 만들어 그 워크플로우로 둔다 → 작업 id."""
    d = client.post("/api/docs?new=1", files={"file": ("a.docx", _docx())}).json()["docId"]
    assert client.put(f"/api/works/{d}/task", json={"kind": "rnd", "file": "report", "job": job, "project": "조립"}).status_code == 200
    return d


def test_definitions_in_use_keep_their_assignment(client):
    """ⓓ 쓰는 곳(C1 · C5) — 그 키를 지금 워크플로우로 둔 작업(inUse)이 있으면 단계(배정 — 원본 · 목적 · llm)를 바꾸지 않고(PUT 409 · 「복제」 로) 지우지 않는다 · 이름 · 설명 · 전제는 고친다.
    문서의 워크플로우 목록에만 든 정의(listed)는 단계를 고칠 수 있지만 지우지는 못한다(DELETE 409 — 새 글) · 목록에서 그 줄을 빼면(C4 DELETE /api/works/{wid}/workflows/{job}) 지운다."""
    from app import custom_tasks_api as API
    t = client.post("/api/tasks", json={"name": "쓰는 중", "assign": {"source": ["stage_review"], "target": ["stage_fill"]}}).json()["task"]
    u = client.post("/api/tasks", json={"name": "목록에만", "assign": {"source": [], "target": ["stage_fill"]}}).json()["task"]
    mine = _work_with(client, t["key"])                # task.job == 그 키
    other = _work_with(client, "plan_to_report")       # 다른 워크플로우 — 문서의 워크플로우 목록에만 그 키(대시보드 이력)
    works.workflow_update(other, u["key"], status="ready", done=0, total=0)
    works.workflow_update(mine, t["key"], status="progress", done=1, total=5)   # 지금 워크플로우의 줄이 목록에도 있다 — 앞(inUse)에만 센다
    assert API.uses(t["key"]) == (1, 0) and API.uses(u["key"]) == (0, 1) and API.uses("u_00000000") == (0, 0) and API.in_use(t["key"]) == 1 and API.in_use(u["key"]) == 0
    got = {x["key"]: x for x in client.get("/api/tasks").json()["tasks"]}
    assert [got[t["key"]][k] for k in ("inUse", "listed", "editWhy", "deleteWhy")] == [1, 0, C.IN_USE.format(n=1), C.DELETE_IN_USE.format(n=1)]
    assert [got[u["key"]][k] for k in ("inUse", "listed", "editWhy", "deleteWhy")] == [0, 1, None, C.DELETE_IN_USE.format(n=1)]
    # D1 — 그 작업들(uses: 지금 워크플로우로 둔 것 active true · 목록에만 든 것 active false) — 이름은 작업 리스트가 보이는 이름(올린 「a.docx」 가 아니라 목적 문서의 프로젝트 이름까지)
    shown = {x["id"]: x["name"] for x in client.get("/api/works").json()}
    assert shown[mine] == works.shown(works.work(mine)) == "a_조립.docx" and shown[other] == works.shown(works.work(other))
    assert got[t["key"]]["uses"] == [{"wid": mine, "name": shown[mine], "project": "조립", "round": 1, "active": True}] and got[t["key"]]["usesMore"] == 0   # 목록에도 있는 지금 워크플로우 — 한 번만
    assert got[u["key"]]["uses"] == [{"wid": other, "name": shown[other], "project": "조립", "round": 1, "active": False}] and got[u["key"]]["usesMore"] == 0
    for body in ({"assign": {"source": ["stage_review"], "target": ["stage_fill", "stage_clean"]}}, {"stages": ["stage_review", "stage_fill", "stage_clean"]}):   # 옛 꼴로 합집합을 바꿔도
        r = client.put(f"/api/tasks/{t['key']}", json=body)
        assert r.status_code == 409 and r.json()["detail"] == C.IN_USE.format(n=1) == got[t["key"]]["editWhy"], r.text   # editWhy 와 같은 글
    ok = client.put(f"/api/tasks/{t['key']}", json={"name": "쓰는 중 — 새 이름", "desc": "설명", "premise": "전제", "assign": {"source": ["stage_review"], "target": ["stage_fill"]}})   # 배정이 그대로 — 됨
    assert ok.status_code == 200 and ok.json()["task"]["name"] == "쓰는 중 — 새 이름" and ok.json()["task"]["assign"] == t["assign"] and ok.json()["task"]["sig"] == t["sig"]
    assert client.put(f"/api/tasks/{u['key']}", json={"stages": ["stage_fill"]}).status_code == 200   # 옛 화면의 같은 합집합 — 배정 그대로라 됨
    e = client.put(f"/api/tasks/{u['key']}", json={"assign": {"source": ["stage_review"], "target": ["stage_fill"]}})   # 목록에만 든 정의 — 단계를 고친다
    assert e.status_code == 200 and e.json()["task"]["assign"]["source"] == ["stage_review"] and e.json()["task"]["listed"] == 1 and e.json()["task"]["editWhy"] is None and e.json()["task"]["sig"] != u["sig"]
    copy = client.post("/api/tasks", json={"name": "쓰는 중 — 새 이름 사본", "assign": t["assign"], "desc": "설명"}).json()["task"]   # 「복제」 — 같은 배정의 새 정의는 고칠 수 있다
    assert copy["assign"] == t["assign"] and client.put(f"/api/tasks/{copy['key']}", json={"assign": {"source": ["stage_review"], "target": ["stage_fill", "stage_clean"]}}).status_code == 200
    for key in (t["key"], u["key"]):   # 지우기 — 지금 워크플로우로 둔 것 · 목록에만 든 것 모두 409(새 글: n = 둘을 더한 수)
        gone = client.delete(f"/api/tasks/{key}")
        assert gone.status_code == 409 and gone.json()["detail"] == C.DELETE_IN_USE.format(n=1), key
    # C4 — 문서의 워크플로우 목록에서 줄 빼기(문서 · 분석은 그대로): 지금 워크플로우 400 · 없는 줄 404 · 빼면 그 정의를 지울 수 있다
    cur = client.delete(f"/api/works/{mine}/workflows/{t['key']}")
    assert cur.status_code == 400 and cur.json()["detail"] == "지금 워크플로우는 목록에서 뺄 수 없습니다 — 다른 워크플로우로 바꾼 뒤에 빼세요"
    nope = client.delete(f"/api/works/{other}/workflows/u_00000000")
    assert nope.status_code == 404 and nope.json()["detail"] == "목록에 그 워크플로우가 없습니다"
    r = client.delete(f"/api/works/{other}/workflows/{u['key']}")
    assert r.status_code == 200 and r.json()["active"] == "plan_to_report" and u["key"] not in [x["job"] for x in r.json()["items"]] and r.json() == client.get(f"/api/works/{other}/workflows").json()
    assert API.uses(u["key"]) == (0, 0) and client.delete(f"/api/tasks/{u['key']}").json() == {"deleted": True}
    assert C.get(t["key"])["assign"] == t["assign"] and API.uses(t["key"]) == (1, 0)
    assert ok.json()["task"]["uses"] == got[t["key"]]["uses"] and e.json()["task"]["uses"][0]["wid"] == other   # PUT 의 응답에도 그 작업들(같은 셈)


def test_uses_lists_the_works_current_first_and_caps_at_twenty(client):
    """D1 — 쓰는 작업이 많으면 uses 는 앞 USES_MAX(20)개 · usesMore = 나머지 수(셈 inUse · listed 는 늘 다 센다). 차례 = 지금 워크플로우로 둔 작업 먼저(최근 바뀐 차례) · 목록에만 든 작업 뒤.
    project · round 는 그 작업의 묶음(프로젝트 · 라운드 — 없으면 "" · 1) · name 은 작업 리스트의 이름(works.shown — 이름이 없으면 id) · 쓰지 않는 정의는 빈 목록."""
    from app import custom_tasks_api as API
    t = C.create({"name": "많이 씀", "assign": {"source": ["stage_review"], "target": ["stage_fill"]}})
    idle = C.create({"name": "안 씀", "assign": {"source": [], "target": ["stage_fill"]}})
    now = [f"{i:012x}" for i in range(1, 23)]                # 지금 워크플로우로 둔 작업 22
    only = [f"{i:012x}" for i in range(0xa1, 0xa4)]          # 목록에만 든 작업 3(지금 워크플로우는 붙박이 이관)
    for n, wid in enumerate(now + only):
        works.create(wid, f"문서{n}.hwpx", "hwpx", b"x")
        works.update(wid, task={"kind": "rnd", "file": "report", "job": t["key"] if wid in now else "plan_to_report", "project": "많이" if n % 2 else ""})
        if wid in only:
            works.workflow_update(wid, t["key"], status="ready", done=0, total=0)
    works.update(now[3], task={"kind": "rnd", "file": "report", "job": t["key"], "project": "많이", "round": 2})   # 가장 최근에 바뀐 작업 — 맨 앞 · 그 라운드
    v = {x["key"]: x for x in client.get("/api/tasks").json()["tasks"]}
    mine = v[t["key"]]
    assert API.USES_MAX == 20 and (mine["inUse"], mine["listed"]) == (22, 3) and len(mine["uses"]) == 20 and mine["usesMore"] == 5   # 22 + 3 − 20
    order = [w["id"] for w in works.list_works()]   # 최근 바뀐 차례
    assert [u["wid"] for u in mine["uses"]] == [w for w in order if w in now][:20] and all(u["active"] for u in mine["uses"])   # 지금 워크플로우 먼저 — 목록에만 든 것은 셈(usesMore)에만
    assert mine["uses"][0] == {"wid": now[3], "name": works.shown(works.work(now[3])), "project": "많이", "round": 2, "active": True}
    assert all(u["name"] == works.shown(works.work(u["wid"])) and u["project"] == works.work(u["wid"])["task"]["project"] and u["round"] == (2 if u["wid"] == now[3] else 1) for u in mine["uses"])
    assert v[idle["key"]]["uses"] == [] and v[idle["key"]]["usesMore"] == 0 and (v[idle["key"]]["inUse"], v[idle["key"]]["listed"]) == (0, 0)
    for wid in now[:20]:   # 지금 워크플로우를 다른 것으로 — 남은 지금 2 + 목록에만 3 = 5: 다 실리고 목록에만 든 것도 보인다(active false · 뒤)
        works.update(wid, task={"kind": "rnd", "file": "report", "job": "plan_to_report", "project": ""})
    mine = next(x for x in client.get("/api/tasks").json()["tasks"] if x["key"] == t["key"])
    assert (mine["inUse"], mine["listed"], mine["usesMore"]) == (2, 3, 0) and [u["active"] for u in mine["uses"]] == [True, True, False, False, False]
    assert {u["wid"] for u in mine["uses"]} == set(now[20:]) | set(only)
    js = client.get("/api/tasks.js").text
    assert '"uses"' not in js and '"usesMore"' not in js   # 화면이 스크립트로 읽는 꼴에는 싣지 않는다(작업을 모두 훑지 않게)


def test_broken_store_reads_empty_and_refuses_to_write(client):
    """ⓔ 저장 파일이 있는데 못 읽으면(JSON 이 깨짐 · 머리가 사전이 아님 · tasks 가 목록이 아님) 읽기는 빈 목록 + broken · 쓰기(만들기 · 고치기 · 지우기)는 409 — 파일은 그대로."""
    p = C.path()
    p.parent.mkdir(parents=True, exist_ok=True)
    for text in ('{"version": 2, "tasks": [{"key": "u_0000aaaa", "name": "깨짐"', "[1, 2]", '{"tasks": {"u_0000aaaa": 1}}'):
        p.write_text(text, encoding="utf-8")
        assert C.all() == [] and C.broken() and C.get("u_0000aaaa") is None, text
        v = client.get("/api/tasks").json()
        assert v["tasks"] == [] and v["broken"] is True, text
        assert client.get("/api/tasks.js").text.endswith('taskCatalogCustom([], {"broken": true});\n'), text   # C3 — 화면이 스크립트로 읽는 글에도 까닭
        with pytest.raises(C.Refused, match=re.escape(C.BROKEN.format(name=p.name))):
            C.create({"name": "새", "assign": {"source": ["stage_review"], "target": []}})
        r = client.post("/api/tasks", json={"name": "새", "assign": {"source": ["stage_review"], "target": []}})
        assert r.status_code == 409 and r.json()["detail"] == "저장 파일(tasks.json)을 읽지 못해 쓰지 않습니다 — 파일을 고치거나 옮긴 뒤 다시 하세요", text
        assert client.put("/api/tasks/u_0000aaaa", json={"name": "x"}).status_code == 409 and client.delete("/api/tasks/u_0000aaaa").status_code == 409, text
        assert p.read_text(encoding="utf-8") == text, text   # 덮어쓰지 않았다
    p.write_text('{"version": 1}', encoding="utf-8")   # tasks 가 없는 머리 — 빈 저장소(쓸 수 있음)
    assert not C.broken() and client.get("/api/tasks").json()["broken"] is False and C.create({"name": "새", "assign": {"source": ["stage_review"], "target": []}})["key"]


def test_a_read_error_is_broken_for_that_call_only(monkeypatch):
    """S2 — 읽기 오류(OSError — 다른 프로세스가 바꿔 넣는 중 · 권한)는 그 호출만 못 읽은 것(broken — 쓰지 않음)으로 보고 남기지 않는다: 파일이 그대로여도 다음 호출이 다시 읽어 정상.
    남기는 것은 읽어서 해석한 결과뿐(정상 · JSON 이 깨짐)."""
    t = C.create({"name": "멀쩡함", "assign": {"source": ["stage_review"], "target": []}})
    p, real, fail = C.path(), C.Path.read_bytes, {"n": 0}

    def flaky(self):
        if self == p and fail["n"]:
            fail["n"] -= 1
            raise PermissionError("바꿔 넣는 중")
        return real(self)

    monkeypatch.setattr(C.Path, "read_bytes", flaky)
    C._CACHE.update(path=None, mtime=None, data=None)   # 파일을 다시 읽게
    fail["n"] = 1
    stamp = p.stat().st_mtime_ns
    assert C.broken() and fail["n"] == 0   # 그 호출만 — 못 읽음
    assert p.stat().st_mtime_ns == stamp and not C.broken() and [x["key"] for x in C.all()] == [t["key"]]   # 파일은 그대로인데 다음 호출이 다시 읽어 정상(못 읽은 것을 남기지 않았다)
    C._CACHE.update(path=None, mtime=None, data=None)
    fail["n"] = 1
    with pytest.raises(C.Refused):   # 못 읽은 호출에서는 쓰지 않는다
        C.create({"name": "또", "assign": {"source": ["stage_review"], "target": []}})
    assert [x["key"] for x in C.all()] == [t["key"]] and p.stat().st_mtime_ns == stamp   # 다음 호출은 정상 — 파일은 그대로


def test_name_only_edits_keep_the_stored_stages_and_the_sig(client):
    """S8 · C1 — 배정이 그대로인 고치기(이름 · 설명 · 전제만 · 같은 배정)는 저장된 줄의 assign · stages 를 읽은 그대로 둔다(이 판이 모르는 단계 id 도 남는다) — 고친 칸만 다시 쓴다.
    sig(단계의 지문)는 이름 · 설명 · 전제만 고치면 그대로, 단계를 바꾸면 바뀐다."""
    p = C.path()
    row = {"key": "u_0000f00d", "name": "다음 판의 줄", "desc": "  빈칸  그대로 ", "source": "plan", "target": "report",
           "assign": {"source": ["stage_review"], "target": ["stage_fill", "stage_future"], "llm": ["source"]}, "stages": ["stage_review", "stage_fill", "stage_future"], "premise": "", "at": 1.0}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": 1, "tasks": [row]}, ensure_ascii=False), encoding="utf-8")
    sig = client.get("/api/tasks").json()["tasks"][0]["sig"]
    assert C.get("u_0000f00d")["assign"]["target"] == ["stage_fill"] and sig == C.sig(C.get("u_0000f00d"))   # 모르는 id 는 보이지 않을 뿐
    r = client.put("/api/tasks/u_0000f00d", json={"name": "이름만 고침"})
    saved = json.loads(p.read_text(encoding="utf-8"))["tasks"][0]
    assert r.status_code == 200 and r.json()["task"]["sig"] == sig and saved == {**row, "name": "이름만 고침"}   # assign · stages(모르는 id 까지) · 보내지 않은 desc 는 읽은 그대로
    client.put("/api/tasks/u_0000f00d", json={"desc": "고친 설명", "premise": "고친 전제", "assign": {"source": ["stage_review"], "target": ["stage_fill"]}})   # 같은 배정 — 고친 칸만
    saved = json.loads(p.read_text(encoding="utf-8"))["tasks"][0]
    assert saved == {**row, "name": "이름만 고침", "desc": "고친 설명", "premise": "고친 전제"} and client.get("/api/tasks").json()["tasks"][0]["sig"] == sig
    before = p.read_text(encoding="utf-8")
    assert C.update("u_0000f00d", {"name": "이름만 고침"})["name"] == "이름만 고침" and p.read_text(encoding="utf-8") == before   # 바뀐 것이 없으면 쓰지 않는다
    moved = client.put("/api/tasks/u_0000f00d", json={"assign": {"source": ["stage_review"], "target": ["stage_fill", "stage_clean"]}}).json()["task"]   # 단계를 바꿈 — 새 배정을 쓴다 · sig 가 바뀐다
    saved = json.loads(p.read_text(encoding="utf-8"))["tasks"][0]
    assert moved["sig"] != sig and saved["assign"]["target"] == ["stage_fill", "stage_clean"] and saved["stages"] == ["stage_review", "stage_fill", "stage_clean"]


def test_malformed_rows_survive_the_next_write(client):
    """ⓕ 꼴이 틀린 줄(모르는 문서 쌍 · stages 가 목록이 아닌 옛 줄 · 고른 것이 없는 새 꼴(옛 stages 로 되살리지 않음) · 겹친 키 · 사전이 아닌 줄)은 목록에 안 보이고
    다음 쓰기 뒤에도 원래 모습 그대로 파일에 남는다 — 머리의 모르는 키도. 고친 줄은 저장하는 키 밖의 키를 지킨다.
    S6 — 지우기는 그 키의 줄을 모두 뺀다(보이는 줄 · 같은 키로 숨은 뒤 줄 · 꼴이 틀린 같은 키의 줄) — 지운 키가 다른 내용으로 되살아나지 않는다."""
    p = C.path()
    good = {"key": "u_0000aaaa", "name": "멀쩡함", "desc": "", "source": "plan", "target": "report", "assign": {"source": ["stage_review"], "target": ["stage_fill"], "llm": ["source"]},
            "stages": ["stage_review", "stage_fill"], "premise": "", "at": 1.0, "future": {"x": 1}}
    bad = [{"key": "u_0000bbbb", "name": "모르는 쌍", "source": "report", "target": "plan", "stages": ["stage_fill"]},
           {"key": "u_0000cccc", "name": "옛 줄 — stages 가 글", "source": "plan", "target": "report", "stages": "stage_fill"},
           {"key": "u_0000dddd", "name": "고른 것 없음", "source": "plan", "target": "report", "assign": {"source": [], "target": ["stage_future"]}, "stages": ["stage_fill"]},
           {**good, "name": "겹친 키"}, "줄이 아님", {"key": "u_0000eeee", "name": "assign 이 목록", "source": "plan", "target": "report", "assign": ["stage_fill"], "stages": ["stage_fill"]},
           {"key": "u_0000aaaa", "name": "꼴이 틀린 같은 키", "source": "report", "target": "plan", "stages": ["stage_fill"]}]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": 7, "tasks": [good] + bad, "note": "다른 서버의 머리 키"}, ensure_ascii=False), encoding="utf-8")
    assert [t["key"] for t in C.all()] == ["u_0000aaaa"] and not C.broken() and [t["key"] for t in client.get("/api/tasks").json()["tasks"]] == ["u_0000aaaa"]
    made = C.create({"name": "새 것", "assign": {"source": ["stage_review"], "target": []}})
    assert made["key"] not in {"u_0000aaaa", "u_0000bbbb", "u_0000cccc", "u_0000dddd", "u_0000eeee"}
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["tasks"][:8] == [good] + bad and saved["note"] == "다른 서버의 머리 키" and saved["version"] == 8 and len(saved["tasks"]) == 9
    C.update("u_0000aaaa", {"desc": "고침"})
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["tasks"][0]["desc"] == "고침" and saved["tasks"][0]["future"] == {"x": 1} and saved["tasks"][1:8] == bad   # 고친 줄의 모르는 키 · 다른 줄은 그대로
    assert C.delete("u_0000aaaa")   # S6 — 그 키의 줄을 모두(보이던 줄 · 겹친 키로 숨은 줄 · 꼴이 틀린 같은 키의 줄) — 숨은 줄이 그 키로 되살아나지 않는다
    assert json.loads(p.read_text(encoding="utf-8"))["tasks"] == [bad[0], bad[1], bad[2], bad[4], bad[5], made]
    assert [t["key"] for t in C.all()] == [made["key"]] and C.get("u_0000aaaa") is None and not C.delete("u_0000aaaa")
    many = [{**good, "key": f"u_{i:08x}", "name": f"줄 {i}"} for i in range(C.TASKS_MAX + 2)]   # 한도 뒤의 줄도 지우지 않는다(안 보일 뿐)
    p.write_text(json.dumps({"version": 1, "tasks": many}, ensure_ascii=False), encoding="utf-8")
    assert len(C.all()) == C.TASKS_MAX and C.update(many[0]["key"], {"desc": "x"}) and len(json.loads(p.read_text(encoding="utf-8"))["tasks"]) == C.TASKS_MAX + 2


# ---------------------------------------------------------------- 정의 v2 — 문서 칸 + 묶음 › 줄(spec_워크플로우 ② §18-5 · 고친 규칙 ② §18-12 ④ · ⑤)
def _c(A):
    return {"key": "u_00000000", "name": "x", "desc": "", "source": "plan", "target": "report", "assign": A, "stages": C.union(A), "premise": "", "at": 0}


def _allowed():
    """허용되는 배정 전부(원본 [] · [문서 검토] × 목적 넷의 부분집합 × llm = 규칙의 부분집합 — 옛 줄의 「원본만」 포함) — 원본 문서를 쓰는 단계가 없는 것은 뺀다."""
    for src in ([], ["stage_review"]):
        for dst in _ROLE_SETS:
            core = {"source": src, "target": dst}
            if not C.union({**core, "llm": []}) or (not src and not any(s in dst for s in C.SOURCE_USE)):
                continue
            rule = C.llm_rule(core)
            for n in range(len(rule) + 1):
                for llm in itertools.combinations(rule, n):
                    yield {**core, "llm": list(llm)}


def _pair(*keys):
    return [{"unit": k} for k in keys]


def test_every_standard_assignment_round_trips_through_the_line_list():
    """⑤ 옛 줄을 읽는 기준 = 지금 등록부(assemble)가 그 배정으로 짓는 줄 목록 — 그 줄 목록을 다시 검사하면 같은 배정(llm 까지 — 유료 대상이 그대로)이고 묶음 id 는 표준 것."""
    n = 0
    for A in _allowed():
        flow = C.flow_of(_c(A))
        got = C.check("relay", "plan", "report", flow)
        assert not got["errors"] and got["std"] == A, (A, got["errors"], got["std"])
        assert [g["id"] for g in got["flow"]] == [C.STAGE_GROUP[m] for m in C.STAGES if m in C.union(A)], A
        n += 1
    assert n >= 28
    # 옛 줄(assign 없이 stages 만)도 — 읽은 배정(from_stages: 1단계 LLM 은 원본만)으로 지은 줄이 표준
    for stages in (["stage_review", "stage_fill"], ["stage_fit"], ["stage_review", "stage_fit", "stage_fill", "stage_clean"]):
        old = C._clean_one({"key": "u_0000000a", "name": "옛", "source": "plan", "target": "report", "stages": stages})
        assert C.check("relay", "plan", "report", C.flow_of(old))["std"] == old["assign"], stages


def test_a_changed_order_is_not_standard_and_wrong_orders_are_refused():
    """표준이 아닌 것: 묶음을 쪼갬 · 묶음 이름을 바꿈 · 묶음을 뺌. 거절: 효과의 차례(구조 반영은 연결 · 넣기 · 정리 앞 · 정리는 반영 뒤) · 먼저 있어야 할 것 · 놓을 수 없는 문서 · 같은 문서에 두 번 ·
    원본을 쓰는 줄 없음 · 준비 줄 · 빈 묶음 · 아직 못 여는 틀(취합형) · 사람이 하는 일(실행기가 멈추는 길이 서기 전) · 하는 문서 없음."""
    std = C.flow_of(_c({"source": ["stage_review"], "target": list(C.STAGES), "llm": ["source"]}))
    split = [dict(std[0], steps=std[0]["steps"][:1]), dict(std[0], steps=std[0]["steps"][1:]), *std[1:]]
    renamed = [dict(std[0], name="처음"), *std[1:]]
    for flow in (split, renamed):
        got = C.check("relay", "plan", "report", flow)
        assert not got["errors"] and got["std"] is None and [g["id"] for g in got["flow"]] == [f"g{i + 1}" for i in range(len(flow))], got
    assert C.check("relay", "plan", "report", std[:-1])["std"] is not None   # 마지막 묶음(문서 정리)을 통째로 뺀 것은 다른 표준 배정
    bad = {
        "구성 반영」 은 「자리 연결」": [{"name": "a", "steps": _pair("link", "plan", "apply") + [{"unit": "division", "on": ["target"]}]}],
        "「내용 반영」 뒤에": [{"name": "a", "steps": _pair("link", "plan") + [{"unit": "guide", "on": ["target"]}] + _pair("apply")}],
        "원본 문서의 「다시 문서 검토(LLM)」 은 그 문서의": [{"name": "a", "steps": [{"unit": "config"}, {"unit": "division", "on": ["source", "target"]}, {"unit": "reheads", "on": ["target"]},
                                                                     {"unit": "reheadsLlm", "on": ["source", "target"]}]}],
        "「다시 문서 검토」 에는 「프로젝트 구성 반영」": [{"name": "a", "steps": [{"unit": "config"}, {"unit": "division", "on": ["target"]}, {"unit": "reheads", "on": ["source", "target"]}]}],   # 원본 문서의 구조 반영 없이 원본을 다시 검토
        "「자리 연결」 뒤에": [{"name": "a", "steps": _pair("plan", "link")}],
        "「표 안 연결 · 넣기 계획」": [{"name": "a", "steps": _pair("link", "apply")}],
        "「다시 문서 검토」 뒤에": [{"name": "a", "steps": [{"unit": "config"}, {"unit": "division", "on": ["target"]}, {"unit": "reheadsLlm", "on": ["target"]}]}],
        "원본 문서를 쓰는 줄이 없습니다": [{"name": "a", "steps": [{"unit": "heads", "on": ["target"]}, {"unit": "guide", "on": ["target"]}]}],
        "놓을 수 없는 줄": [{"name": "a", "steps": [{"unit": "files"}, {"unit": "heads", "on": ["source"]}]}],
        "줄이 없습니다": [{"name": "빈 묶음", "steps": []}, {"name": "b", "steps": [{"unit": "heads", "on": ["source"]}]}],
        "할 문서를 고르세요": [{"name": "a", "steps": [{"unit": "heads", "on": []}]}],
    }
    for word, flow in bad.items():
        got = C.check("relay", "plan", "report", flow)
        assert any(word in e for e in got["errors"]), (word, got["errors"])
    got = C.check("gather", "plan", "report", std)   # 취합형은 2026-11-20 엶(② §18-13 갈래 「라」 — 그 조립은 tests/test_workflow_gather.py) — 이관의 문서 쌍 · 이관의 줄은 그 틀에 놓지 못한다
    assert any("기관 문서 → 사업계획서" in e for e in got["errors"]) and any("놓을 수 없는 줄" in e for e in got["errors"]) and not any("취합은 아직" in e for e in got["errors"]), got["errors"]
    got = C.check("single", "plan", "report", std)   # 문서 하나는 2026-11-20 엶(② §18-13 갈래 「라」 — 문서 하나: 그 조립은 tests/test_custom_single.py) — 원본이 있는 짝 · 이관의 줄은 그 틀에 놓지 못한다
    assert any("원본 문서는 없습니다" in e for e in got["errors"]) and any("놓을 수 없는 줄" in e for e in got["errors"]) and not any("문서 하나 워크플로우는 아직" in e for e in got["errors"]), got["errors"]
    assert C.check("relay", "plan", "report", "x")["errors"] == ["묶음을 하나 이상 두세요"]
    # 사람이 하는 일(⑦ — 실행기가 그 줄에서 멈추고 「했음」 을 기다린다): 놓을 수 있고 여럿도 되고 표준이 아니다 · 줄 id 는 hand1 · hand2 …(겹치면 새로)
    got = C.check("relay", "plan", "report", [{"name": "a", "steps": [{"unit": "heads", "on": ["source"]}, {"unit": "hand", "on": ["target"], "name": "확인", "id": "hand1"},
                                                                    {"unit": "hand", "on": ["target"], "name": "또 확인", "id": "hand1"}]}])
    assert not got["errors"] and got["std"] is None and [s.get("id") for s in got["flow"][0]["steps"]] == [None, "hand1", "hand2"], got
    # 경고(막지 않음) — 원본만 검토 → 이미 구성된 목적 문서에 내용 넣기(⑤ 의 끝: 표준 네 묶음으로는 나타낼 수 없던 정의)
    got = C.check("relay", "plan", "report", [{"name": "원본 검토", "steps": [{"unit": "heads", "on": ["source"]}, {"unit": "headsLlm", "on": ["source"]}]},
                                                {"name": "넣기", "steps": _pair("link", "plan", "apply")}])
    assert not got["errors"] and got["std"] is None, got
    assert any("목적 문서의 「헤딩 · 표 분석」" in w for w in got["warns"]) and any("「프로젝트 구성 반영」 이 없습니다" in w for w in got["warns"]) and any(w.startswith("유료 LLM") for w in got["warns"])


def test_a_line_may_be_placed_again_and_two_documents_may_share_a_turn():
    """2026-11-20 사용자 「이걸 같이 실행할 수 있는 기능이 없음. 그리고 도구는 1번 이상 선택할 수 있어야지 한번 하고 두번 선택이 안되냐」(② §18-6 「행 × 두 칸」):
    ⓐ 같은 줄을 (같은 문서에) 두 번 넘게 놓는 것은 거절이 아니라 경고 — 문서 줄 · 원본 → 목적 줄 모두 · 표준 차례가 아니다(줄 목록으로).
    ⓑ 줄의 `beside` = 앞 줄과 같은 차례(조립 화면의 같은 행) — 다른 문서 하나의 줄 바로 뒤에서만 남고(그 밖에는 조용히 지운다) · 표준 차례가 아니며 · 지문(sig)에 들지 않고 · 저장 · 다시 읽기에 남는다."""
    again = [{"name": "a", "steps": [{"unit": "heads", "on": ["source", "target"]}, {"unit": "config"}, {"unit": "division", "on": ["target"]}, {"unit": "heads", "on": ["target"]},
                                     {"unit": "reheads", "on": ["target"]}] + _pair("link", "plan", "apply", "plan", "apply")}]
    got = C.check("relay", "plan", "report", again)
    assert not got["errors"] and got["std"] is None, got["errors"]
    assert any(w.startswith("「헤딩 · 표 분석」 을 목적 문서에 두 번 넘게 놓았습니다") and w.endswith(C.AGAIN) for w in got["warns"]), got["warns"]
    assert any(w.startswith("「내용 반영」 을 두 번 넘게 놓았습니다") for w in got["warns"]) and not any("원본 문서에 두 번" in w for w in got["warns"]), got["warns"]
    assert [s["unit"] for s in got["flow"][0]["steps"]].count("apply") == 2   # 줄은 놓은 그대로(합치지 않는다)
    # ⓑ 같은 차례 — 원본 문서 줄 옆에 목적 문서의 다른 줄
    row = lambda *steps: [{"name": "a", "steps": list(steps)}]  # noqa: E731
    side = row({"unit": "heads", "on": ["source"]}, {"unit": "hand", "on": ["target"], "name": "확인", "beside": True}, {"unit": "headsLlm", "on": ["source"]})
    got = C.check("relay", "plan", "report", side)
    assert not got["errors"] and got["std"] is None and [bool(s.get("beside")) for s in got["flow"][0]["steps"]] == [False, True, False], got
    plain = C.check("relay", "plan", "report", row(*[{k: v for k, v in s.items() if k != "beside"} for s in side[0]["steps"]]))
    assert C.sig({"shape": "relay", "source": "plan", "target": "report", "flow": got["flow"]}) == C.sig({"shape": "relay", "source": "plan", "target": "report", "flow": plain["flow"]})   # 보이는 꼴 — 지문 밖
    assert C._flow_text(got["flow"]) != C._flow_text(plain["flow"])   # 그래도 고친 것으로 저장된다(update 가 견주는 글)
    # 표준 차례에 같은 차례 표시를 얹으면 줄 목록으로(옛 꼴은 그 표시를 지니지 못한다) — 원본만 검토(헤딩 · 표 분석 → LLM 검증·보완은 같은 문서라 표시가 지워지고 표준 그대로)
    std = C.flow_of(_c({"source": ["stage_review"], "target": [], "llm": ["source"]}))
    same_doc = [dict(std[0], steps=[std[0]["steps"][0], dict(std[0]["steps"][1], beside=True)]), *std[1:]]
    got = C.check("relay", "plan", "report", same_doc)
    assert got["std"] is not None and not any(s.get("beside") for s in got["flow"][0]["steps"]), got   # 같은 문서의 줄 뒤 — 지움
    # 지우는 꼴: 묶음의 첫 줄 · 두 문서 줄 뒤 · 원본 → 목적 줄 뒤 · 앞 줄이 이미 옆에 선 줄(행이 찼다) · 문서마다가 아닌 줄
    for steps, want in (([{"unit": "heads", "on": ["target"], "beside": True}, {"unit": "heads", "on": ["source"]}], [False, False]),
                        ([{"unit": "heads", "on": ["source", "target"]}, {"unit": "headsLlm", "on": ["source"], "beside": True}], [False, False]),
                        ([{"unit": "heads", "on": ["source"]}, {"unit": "heads", "on": ["target"], "beside": True}, {"unit": "headsLlm", "on": ["source"], "beside": True}], [False, True, False]),
                        (_pair("link") + [{"unit": "hand", "on": ["target"], "name": "확인", "beside": True}], [False, False]),
                        ([{"unit": "heads", "on": ["source"]}, {"unit": "config", "beside": True}], [False, False])):
        got = C.check("relay", "plan", "report", row(*steps))
        assert [bool(s.get("beside")) for s in got["flow"][0]["steps"]] == want, (steps, got["flow"])
    # 저장 · 다시 읽기 — beside 가 남는다 · 표시만 바꿔도 저장된다(쓰는 중이어도: 지문이 그대로)
    made = C.create({"name": "같은 차례", "flow": side})
    assert made["v"] == 2 and [bool(s.get("beside")) for s in C.get(made["key"])["flow"][0]["steps"]] == [False, True, False]
    apart = [dict(g, steps=[{k: v for k, v in s.items() if k != "beside"} for s in g["steps"]]) for g in C.get(made["key"])["flow"]]
    C.update(made["key"], {"flow": apart}, busy=1)
    assert not any(s.get("beside") for s in C.get(made["key"])["flow"][0]["steps"]) and C.sig(C.get(made["key"])) == C.sig(made)
    C.delete(made["key"])


def test_workflow_wide_lines_stand_in_one_column_and_every_checked_definition_assembles():
    """2026-11-20 사용자 「양쪽에 걸쳐 있는 것들은 왜 분리가 안되고 붙어 있나? 의미가 없는데」(② §18-6 「행 × 두 칸」 「워크플로우 전체 줄」): 워크플로우 전체 줄(구성 불러오기 · 프로젝트 구성 추출)은 두 칸에 걸치지 않고 한 칸에 선다 —
    ⓐ 처음 서는 칸 = 구성 불러오기는 목적 문서 · 프로젝트 구성 추출은 구성의 기준 문서(이관 = 원본 · 취합 = 목적) — 고를 줄 API 가 싣는다 ⓑ 다른 칸에 놓으면 줄의 `col`(처음 칸이면 지운다 · 문서 줄 · 원본 → 목적 줄의 것은 지운다) ·
    표준 차례가 아니고(줄 목록으로) 지문 밖 ⓒ 다른 칸의 줄과 같은 차례(beside)에 설 수 있다(같은 칸이면 지운다).
    그리고 조립 검사가 통과시킨 정의는 모두 지어진다 — 「LLM 검증·보완」 을 「헤딩 · 표 분석」 이 없는 문서에 놓은 정의가 저장된 뒤 목록 · /workflow 를 500 으로 만들던 것(KeyError)의 되풀이 막이."""
    from app import custom_tasks_api as A
    from app import workflow
    assert {u["key"]: u.get("col") for u in A.units() if u["place"] == "flow"} == {"configLoad": "target", "config": "source", "take": "target"}   # take = 「넣을 구성 선택」(조립에 놓는 도구 — 목적 문서 칸)
    assert {u["key"]: u.get("col") for u in A.gather_units()[0] if u["place"] == "flow"} == {"config": "target"} and all("col" not in u for u in A.units() if u["place"] != "flow")
    assert (C.col_of("config"), C.col_of("configLoad"), C.col_of("config", "gather")) == ("source", "target", "target")
    std = C.flow_of(_c({"source": ["stage_review"], "target": list(C.STAGES), "llm": ["source"]}))
    with_col = lambda col: [dict(g, steps=[dict(s, **({"col": col(s["unit"])} if s["unit"] in ("config", "configLoad") else {})) for s in g["steps"]]) for g in std]  # noqa: E731
    got = C.check("relay", "plan", "report", with_col(C.col_of))
    assert got["std"] is not None and not any(s.get("col") for g in got["flow"] for s in g["steps"])   # 처음 서는 칸 — 적지 않는다(표준 차례 그대로)
    got = C.check("relay", "plan", "report", with_col(lambda u: "target"))
    assert not got["errors"] and got["std"] is None and {s["unit"]: s.get("col") for g in got["flow"] for s in g["steps"] if s["unit"] in ("config", "configLoad")} == {"config": "target", "configLoad": None}
    plain = C.check("relay", "plan", "report", std)
    assert C.sig({"shape": "relay", "source": "plan", "target": "report", "flow": got["flow"]}) != ""   # 지문은 줄의 칸과 무관하다(묶음 id 만 표준 → g1 … 로 달라진다)
    assert C._flow_text(got["flow"]) != C._flow_text(plain["flow"])
    row = lambda *steps: [{"name": "a", "steps": list(steps)}]  # noqa: E731
    got = C.check("relay", "plan", "report", row({"unit": "heads", "on": ["source", "target"]}, {"unit": "config"}, {"unit": "configLoad", "beside": True}, {"unit": "division", "on": ["target"]},
                                                 {"unit": "heads", "on": ["source"]}, {"unit": "configLoad", "col": "target", "beside": True}))
    assert not got["errors"] and [(s["unit"], s.get("col"), bool(s.get("beside"))) for s in got["flow"][0]["steps"]] == [
        ("heads", None, False), ("config", None, False), ("configLoad", None, True), ("division", None, False), ("heads", None, False), ("configLoad", None, True)], got
    got = C.check("relay", "plan", "report", row({"unit": "config", "col": "target"}, {"unit": "configLoad", "beside": True}, {"unit": "heads", "on": ["source"], "col": "target"}, {"unit": "link", "col": "source"}))
    assert [(s["unit"], s.get("col"), bool(s.get("beside"))) for s in got["flow"][0]["steps"]] == [("config", "target", False), ("configLoad", None, False), ("heads", None, False), ("link", None, False)], got["flow"]
    # 조립 검사가 통과시킨 정의는 지어진다 — 문서 줄 하나 · 둘(그 뒤에 넣기 줄이 있거나 없거나)
    kinds, n = ("heads", "headsLlm", "division", "reheads", "reheadsLlm", "guide"), 0
    for a in kinds:
        for ra in (["source"], ["target"], ["source", "target"]):
            for b, rb in [(None, None), *[(k, [r]) for k in kinds for r in ("source", "target")]]:
                steps = [{"unit": "config"}, {"unit": a, "on": ra}, *([{"unit": b, "on": rb}] if b else [])]
                for flow in (row(*steps), row(*steps, *_pair("link", "plan", "apply"))):
                    got = C.check("relay", "plan", "report", flow)
                    if got["errors"]:
                        continue
                    n += 1
                    t = workflow.assemble({"key": "u_0000000a", "name": "지어 보기", "desc": "", "premise": "", "at": 0, "shape": "relay", "source": "plan", "target": "report", "assign": None, "stages": [], "v": 2, "flow": got["flow"]})
                    assert [s["key"] for g in t["stages"] for s in g["steps"] if s["key"] != "files"] == [s["unit"] for g in got["flow"] for s in g["steps"]], (a, ra, b, rb)
    assert n > 100
    llm_only = workflow.assemble({"key": "u_0000000a", "name": "LLM 만", "desc": "", "premise": "", "at": 0, "shape": "relay", "source": "plan", "target": "report", "assign": None, "stages": [], "v": 2,
                                  "flow": C.check("relay", "plan", "report", row({"unit": "heads", "on": ["source"]}, {"unit": "headsLlm", "on": ["target"]}))["flow"]})
    line = next(s for g in llm_only["stages"] for s in g["steps"] if s["key"] == "headsLlm")
    assert line["on"] == "target" and "연차보고서" in line["does"]
    # 같은 차례의 표시는 등록부 꼴의 줄에도 실린다(실행기가 그 두 줄을 함께 돌지 본다)
    side = workflow.assemble({"key": "u_0000000a", "name": "같은 차례", "desc": "", "premise": "", "at": 0, "shape": "relay", "source": "plan", "target": "report", "assign": None, "stages": [], "v": 2,
                              "flow": C.check("relay", "plan", "report", row({"unit": "heads", "on": ["source"]}, {"unit": "hand", "on": ["target"], "name": "확인", "beside": True}))["flow"]})
    assert [bool(s.get("beside")) for g in side["stages"] for s in g["steps"] if s["key"] != "files"] == [False, True]


def test_document_lines_go_on_the_source_document_too_apart_or_together():
    """2026-11-20 사용자 「원본 문서는 왜 네 맘대로 빼냐? 목적문서랑 원본 문서도 분리해서 따로 따로 하게 해줘야지. 다만 동일하게 같이 작업해야 한다는 기능이 있으면 더 좋겠지」(② §18-2 「원본 문서에 놓는 줄」):
    구성 반영 · 다시 문서 검토 · 작성요령 삭제를 원본 문서에도 놓는다 — 한 줄에 두 문서(같이) · 문서마다 다른 줄(따로: 원본이 앞). 표준 차례가 아니고(v2), 바꾸는 문서를 문서마다 알린다 · 등록부의 줄 · 글이 그 문서를 따른다."""
    from app import workflow
    both = ["source", "target"]
    together = [{"name": "검토", "steps": [{"unit": "heads", "on": both}]},
                {"name": "구성", "steps": [{"unit": "config"}, {"unit": "division", "on": both}, {"unit": "reheads", "on": both}, {"unit": "reheadsLlm", "on": ["source"]}]},
                {"name": "넣기", "steps": _pair("link", "plan", "apply") + [{"unit": "guide", "on": both}]}]
    got = C.check("relay", "plan", "report", together)
    assert not got["errors"] and got["std"] is None, got
    assert "목적 문서를 바꾸는 줄: 프로젝트 구성 반영 · 내용 반영 · 작성요령 삭제" in got["warns"] and "원본 문서를 바꾸는 줄: 프로젝트 구성 반영 · 작성요령 삭제" in got["warns"], got["warns"]
    assert not any("다시 문서 검토」 가" in w for w in got["warns"])   # 두 문서 다 구조 반영 뒤 다시 검토가 있다
    apart = [{"name": "a", "steps": [{"unit": "heads", "on": both}, {"unit": "config"}, {"unit": "division", "on": ["source"]}, {"unit": "reheads", "on": ["source"]},
                                     {"unit": "division", "on": ["target"]}, {"unit": "reheads", "on": ["target"]}] + _pair("link", "plan", "apply")}]
    assert not C.check("relay", "plan", "report", apart)["errors"]
    # 문서끼리의 차례는 자유다(사용자 「프로젝트 구성을 완료하고 문서 검토하고 다른문서 프로젝트 구성할 수도 있잖아」) — 목적 문서의 구성 반영 · 다시 검토를 끝낸 뒤 원본 문서의 구성 반영 · 다시 검토
    later = [{"name": "a", "steps": [{"unit": "heads", "on": both}, {"unit": "config"}, {"unit": "division", "on": ["target"]}, {"unit": "reheads", "on": ["target"]}, {"unit": "reheadsLlm", "on": ["target"]},
                                     {"unit": "division", "on": ["source"]}, {"unit": "reheads", "on": ["source"]}] + _pair("link", "plan", "apply")}]
    got = C.check("relay", "plan", "report", later)
    assert not got["errors"] and got["std"] is None, got
    only =[{"name": "a", "steps": [{"unit": "heads", "on": both}, {"unit": "config"}, {"unit": "division", "on": ["source"]}] + _pair("link", "plan", "apply")}]   # 원본 문서만 구조 반영 · 다시 검토 없이 자리 연결
    got = C.check("relay", "plan", "report", only)
    assert not got["errors"] and any(w.startswith("원본 문서의 구조를 바꾼 뒤 원본 문서의 「다시 문서 검토」 가 「자리 연결」 앞에 없습니다") for w in got["warns"]), got
    assert any("「프로젝트 구성 반영」 을 원본 문서에만 합니다" in w for w in got["warns"])
    # 등록부 꼴 — 줄의 하는 문서 · 글 · 묶음이 바꾸는 문서 · 원본이 바뀐다는 글(「바뀌지 않는 문서」 라는 말은 싣지 않는다)
    c = {"key": "u_0000000b", "name": "두 문서 구성", "desc": "", "source": "plan", "target": "report", "shape": "relay", "flow": C.check("relay", "plan", "report", together)["flow"], "premise": "", "at": 0}
    t = workflow.assemble(c)
    steps = {s["key"]: s for g in t["stages"] for s in g["steps"]}
    assert [steps[k]["on"] for k in ("division", "reheads", "reheadsLlm", "guide")] == ["both", "both", "source", "both"]
    assert steps["division"]["does"].startswith("사업계획서의 구조를 그 문서의 프로젝트 구성 값") and "연차보고서의 값을 사업계획서 기준으로" in steps["division"]["does"]
    assert steps["reheadsLlm"]["out"] == "LLM 검증·보완을 거친 사업계획서의 헤딩 그래프 · 표 구조" and steps["guide"]["out"] == "안내를 지운 두 문서(사업계획서 · 연차보고서)"
    assert t["stages"][1]["does"].endswith(" · 원본 문서 · 목적 문서가 바뀜") and t["stages"][0]["does"].endswith(" · 문서는 안 바뀜")
    assert "사업계획서(원본)도 바뀝니다 — 원본 문서에 놓은 줄: 프로젝트 구성 반영 · 작성요령 삭제." in t["note"] and "바뀌지 않는 문서" not in json.dumps(t, ensure_ascii=False, default=str)
    assert workflow.custom_desc(c).endswith("원본 문서(사업계획서)도 바꿉니다 — 프로젝트 구성 반영 · 작성요령 삭제.")
    # 목적 문서만의 줄은 전과 같은 글(붙박이 이관의 글 그대로)
    std = workflow.assemble({**c, "flow": C.flow_of(_c({"source": ["stage_review"], "target": list(C.STAGES), "llm": ["source"]}))})
    base = {s["key"]: s for g in workflow.task_of("plan_to_report")["stages"] for s in g["steps"]}
    assert all({s["key"]: s for g in std["stages"] for s in g["steps"]}[k]["does"] == base[k]["does"] for k in ("division", "reheads", "reheadsLlm", "guide"))
    assert "사업계획서(원본)는 바뀌지 않습니다." in std["note"]


def test_the_lines_a_line_needs_first_agree_with_the_check():
    """먼저 있어야 할 줄(units[].uses — spec ② §18-6 「대상 잇기」 의 (나)): 화면이 읽는 것과 조립 검사의 판정이 같다 — must 인 앞 줄이 없으면 거절 · must 가 아니면 거절하지 않는다. 취합형은 GATHER_USES."""
    from app import custom_tasks_api as A
    from app import workflow_units as WU
    by = {u["key"]: u["uses"] for u in A.units()}
    assert by["llm"] == by["plan"] == [{"unit": "link", "must": True}] and by["gaps"] == by["tableMap"] == by["apply"] == [{"unit": "plan", "must": True}]
    assert by["reheads"] == [{"unit": "division", "must": True}] and by["reheadsLlm"] == [{"unit": "reheads", "must": True}]
    assert by["headsLlm"] == [{"unit": "heads", "must": False}] and by["division"] == [{"unit": "config", "must": False}] and by["guide"] == [{"unit": "apply", "must": False}]
    assert by["link"] == [{"unit": "heads", "must": False}, {"unit": "reheads", "must": False}] and by["heads"] == by["config"] == by["hand"] == []
    names = C.unit_names()
    for key, uses in by.items():   # 그 줄 하나만 놓은 정의(원본 문서를 쓰는 줄 하나를 곁들임) — must 인 앞 줄이 없으면 그 줄 이름이 든 거절이 있고, 아니면 그런 거절이 없다
        u = WU.unit(key, "relay")
        line = {"unit": key, "on": ["target"]} if u["place"] == "doc" else {"unit": key}
        got = C.check("relay", "plan", "report", [{"name": "a", "steps": [{"unit": "heads", "on": ["source"]}, line] if key != "heads" else [line]}])
        hit = [e for e in got["errors"] if f"「{names[key]}」" in e and ("앞에 있어야" in e or "뒤에 와야" in e)]
        assert bool(hit) == any(x["must"] for x in uses), (key, uses, got["errors"])
    g = {u["key"]: u["uses"] for u in A.gather_units()[0]}
    assert g["apply"] == [{"unit": "plan", "must": True}] and g["plan"] == g["llm"] == [{"unit": "link", "must": True}] and g["link"] == g["division"] == g["hand"] == []
    assert g["retidy"] == [{"unit": "apply", "must": False}]   # 넣은 뒤 템플릿 · 서식 정리(취합 — GATHER_SOFT): 「내용 반영」 이 없어도 거절하지 않는다(경고만)
    alone = C.check("gather", "part", "plan", [{"name": "a", "steps": [{"unit": "retidy", "on": ["target"]}]}])
    assert not alone["errors"] and any("「넣은 뒤 템플릿 · 서식 정리」" in w and "앞서 넣은 내용만" in w for w in alone["warns"]), alone


def test_line_lists_are_stored_as_v2_or_as_the_old_form_and_old_reads_do_not_see_v2(client):
    """⑤ 한 표현만: 표준 차례면 옛 꼴(assign · stages)로 · 아니면 v2(shape · v · flow — assign · stages 없음: 옛 서버는 숨기고 그대로 둔다). 판 없는 읽기(옛 탭)에는 표준 정의만 ·
    옛 화면이 v2 정의의 단계를 고치면 409 · 묶음 이름만 고치면 지문 그대로 · 쓰는 중이면 줄을 못 바꿈(409) · 표준 차례로 되돌리면 옛 꼴로."""
    f2 = [{"name": "원본 검토", "steps": [{"unit": "heads", "on": ["source", "target"]}, {"unit": "headsLlm", "on": ["source"]}]},
          {"name": "넣기", "steps": [{"unit": "link"}, {"unit": "plan"}, {"unit": "apply"}, {"unit": "guide", "on": ["target"]}]}]
    chk = client.post("/api/tasks/check", json={"flow": f2}).json()
    r = client.post("/api/tasks", json={"name": "원본 검토 뒤 넣기", "flow": f2})
    assert r.status_code == 201, r.text
    t = r.json()["task"]
    assert t["v"] == 2 and t["assign"] is None and t["groups"] == ["g1", "g2"] and t["sig"] == chk["sig"] and not chk["std"] and "정한 차례대로" in t["descAuto"]
    row = next(x for x in json.loads(C.path().read_text(encoding="utf-8"))["tasks"] if x["key"] == t["key"])
    assert "assign" not in row and "stages" not in row and row["v"] == 2 and row["flow"][1]["steps"][0] == {"unit": "link", "on": ["source", "target"]}
    assert t["key"] not in [x["key"] for x in client.get("/api/tasks").json()["tasks"]] and client.get("/api/tasks").json()["hidden"] == 1
    assert t["key"] in [x["key"] for x in client.get("/api/tasks?v=2").json()["tasks"]] and t["key"] not in client.get("/api/tasks.js").text and t["key"] in client.get("/api/tasks.js?v=2").text
    W = next(x for x in client.get("/api/workflow").json()["tasks"] if x["job"] == t["key"])
    assert [(g["id"], g["no"], g["name"], [(s["key"], s["on"]) for s in g["steps"]]) for g in W["stages"]] == [
        ("g1", "1단계", "원본 검토", [("files", "flow"), ("heads", "both"), ("headsLlm", "source")]), ("g2", "2단계", "넣기", [("link", "pair"), ("plan", "pair"), ("apply", "pair"), ("guide", "target")])]
    assert "정한 차례: [원본 검토: 「헤딩 · 표 분석」" in workflow.picked_line(C.get(t["key"]))
    put = client.put(f"/api/tasks/{t['key']}", json={"assign": {"source": ["stage_review"], "target": ["stage_fill"]}})
    assert put.status_code == 409 and put.json()["detail"] == C.FLOW_LOCKED
    renamed = client.put(f"/api/tasks/{t['key']}", json={"name": "새 이름", "flow": [dict(f2[0], name="검토"), f2[1]]}).json()["task"]
    assert renamed["name"] == "새 이름" and renamed["sig"] == t["sig"] and renamed["flow"][0]["name"] == "검토"   # 묶음 이름은 지문에 안 든다
    with pytest.raises(C.Refused):
        C.update(t["key"], {"flow": [f2[0], dict(f2[1], steps=f2[1]["steps"][:3])]}, busy=1)
    std = C.flow_of(_c({"source": ["stage_review"], "target": ["stage_fill"], "llm": ["source"]}))
    back = client.put(f"/api/tasks/{t['key']}", json={"flow": std}).json()["task"]
    row = next(x for x in json.loads(C.path().read_text(encoding="utf-8"))["tasks"] if x["key"] == t["key"])
    assert back["v"] == 1 and back["assign"] == {"source": ["stage_review"], "target": ["stage_fill"], "llm": ["source"]} and "flow" not in row and "v" not in row and row["stages"] == ["stage_review", "stage_fill"]
    bad = client.post("/api/tasks", json={"name": "거꾸로", "flow": [{"name": "a", "steps": [{"unit": "plan"}, {"unit": "link"}]}]})
    assert bad.status_code == 400 and "뒤에 와야" in bad.json()["detail"]
    tasks = client.get("/api/tasks?v=2").json()
    assert {u["key"] for u in tasks["units"]} >= {"heads", "headsLlm", "config", "division", "link", "apply", "guide", "hand"} and "files" not in {u["key"] for u in tasks["units"]}
    # 문서 입출력(② §18-8 — 2026-11-20 사용자 "1->N, N-1 문서 입출력"): 꼴 「1」 · 「1 → 1」 · 「N → 1」 · 칸(원본 → 목적 · 수 · 종류) — 아직 못 여는 틀은 까닭과 함께
    sh = {s["id"]: s for s in tasks["shapes"]}
    assert [s["id"] for s in tasks["shapes"]] == ["single", "relay", "gather"] and [s["io"] for s in tasks["shapes"]] == ["1", "1 → N", "N → 1"]   # 이관 = 1 → N(사용자 「이관은 1-N으로」)
    assert not sh["single"]["soon"] and not sh["gather"]["soon"] and not sh["relay"]["soon"]   # 취합형 · 문서 하나 모두 2026-11-20 엶(② §18-13 갈래 「라」 — 문서 하나는 조립한 것만 서버가 돈다)
    assert [(x["role"], x["many"], [k["id"] for k in x["kinds"]]) for x in sh["relay"]["slots"]] == [("source", False, ["plan"]), ("target", True, ["report"])]
    assert [(x["role"], x["many"], [k["name"] for k in x["kinds"]]) for x in sh["gather"]["slots"]] == [("source", True, ["기관 문서"]), ("target", False, ["사업계획서"])]   # 목적 = 취합본(사업계획서)뿐 — 지금 조립할 수 있는 짝(custom_tasks.GATHER_PAIRS)
    assert {u["key"] for u in tasks["byShape"]["gather"]["units"]} == {*C.GATHER_UNITS, "hand"} and [g["name"] for g in tasks["byShape"]["gather"]["flow"]] == ["프로젝트 구성", "문서 프레임 작성", "내용 매핑"]   # 틀마다의 고를 줄 · 처음 줄 목록
    assert [x["role"] for x in sh["single"]["slots"]] == ["target"]
