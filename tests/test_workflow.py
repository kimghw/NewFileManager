"""워크플로우 등록부(spec_워크플로우 — app/workflow.py · app/workflow_api.py) — 서버의 TASK 키 · task_catalog.js · 모듈 파일 · 에이전트 등록부 · 사양서와 어긋나지 않는지 + API · 페이지.
TASK 를 더하거나 TASK 의 단계·모듈·에이전트를 바꾸고 등록부를 잊으면 여기서 떨어진다. 문서 분석·LLM 은 쓰지 않는다."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import agents, server
from app import workflow as W

ROOT = Path(__file__).parents[1]
CATALOG = (ROOT / "app" / "static" / "task_catalog.js").read_text(encoding="utf-8")
CATALOG_JOBS = re.findall(r'^  (\w+): \{ name: "', CATALOG, re.M)                 # TASK_CATALOG 의 키(차례대로)
CATALOG_SOON = set(re.findall(r'^  (\w+): \{ name: "[^\n]*\bsoon: true', CATALOG, re.M))
_META_ROW = r'^  (\w+): \{ no: "([^"]*)", name: "([^"]*)"'
_block = lambda name: re.search(rf"const {name} = Object\.freeze\(\{{(.*?)\n\}}\);", CATALOG, re.S)[1]  # noqa: E731
STAGE_META = {m[0] for m in re.findall(_META_ROW, _block("TASK_STAGE_META"), re.M)}                 # TASK_STAGE_META 의 키(취합의 묶음 이름)
RELAY_META = {m[0]: {"no": m[1], "name": m[2]} for m in re.findall(_META_ROW, _block("RELAY_STAGE_META"), re.M)}   # 이관의 묶음 이름(spec_작업 ② §21) — 등록부의 no·name 과 같아야 한다


def test_catalog_is_read_the_way_this_test_expects():
    assert CATALOG_JOBS[:2] == ["plan_fit", "plan_merge"] and "report_merge" in CATALOG_SOON and STAGE_META >= {"config", "frame", "map", "clean"}


def test_tasks_are_exactly_the_server_tasks_in_catalog_order():
    """새 TASK 를 서버·카탈로그에 넣고 워크플로우를 빠뜨리면(또는 그 반대) 떨어진다."""
    jobs = [t["job"] for t in W.TASKS]
    assert set(jobs) == set(server.TASK["job"]) - {""} and len(jobs) == len(set(jobs))
    assert jobs == CATALOG_JOBS
    assert {t["job"] for t in W.TASKS if t.get("soon")} == CATALOG_SOON
    for t in W.TASKS:
        assert t["inputs"] and t["output"], t["job"]
        assert bool(t["stages"]) != bool(t.get("soon")), f"{t['job']}: 준비 중인 TASK 만 단계 묶음이 없다"


def test_stage_groups_and_steps_are_well_formed():
    for t in W.TASKS:
        ids = [g["id"] for g in t["stages"]]
        assert len(ids) == len(set(ids)), t["job"]
        keys = [s["key"] for g in t["stages"] for s in g["steps"]]
        assert len(keys) == len(set(keys)), f"{t['job']}: 단계 key 가 겹침"
        for g in t["stages"]:
            assert g["steps"] and g["does"], (t["job"], g["id"])
            if g["meta"]:
                assert g["meta"] in STAGE_META and g["meta"] == g["id"], (t["job"], g["id"])   # 이름은 화면이 TASK_STAGE_META 에서 읽는다
            else:
                assert g["name"], (t["job"], g["id"])
    relay = W.BY_JOB["plan_to_report"]["stages"]
    assert [g["id"] for g in relay] == ["review", "frame", "map", "clean"]   # 이관 = 1~4단계(spec_작업 ② §21 — 문서 검토 · 구성 맞추기 · 내용 넣기 · 문서 정리)
    assert {g["id"]: {"no": g["no"], "name": g["name"]} for g in relay} == RELAY_META and all(g["meta"] is None for g in relay)   # 이름은 화면의 RELAY_STAGE_META 와 같다(취합의 TASK_STAGE_META 를 안 쓴다)
    keys = {g["id"]: [s["key"] for s in g["steps"] if not s["optional"]] for g in relay}   # 선택 단계(LLM)를 뺀 차례 — 화면의 TASK_STAGES.keys(app.js)와 같다
    assert keys == {"review": ["files", "heads"], "frame": ["config", "division", "reheads"], "map": ["link", "plan", "apply", "later"], "clean": ["guide"]}
    assert [s["key"] for g in relay for s in g["steps"] if s["optional"]] == ["headsLlm", "reheadsLlm", "llm", "tableMap", "gaps"]
    assert [g["id"] for g in W.BY_JOB["plan_merge"]["stages"]] == ["config", "frame", "map"]                # 취합 = 1~3단계
    ids = [c["id"] for c in W.COMMON]
    assert len(ids) == len(set(ids)) and all(c["name"] and c["does"] and c["where"] and c["steps"] for c in W.COMMON)
    for where, s in W.steps():
        assert s["name"] and s["does"] and s["by"] and set(s["by"]) <= set(W.BY) and s["change"] in W.CHANGE, (where, s["key"])
        assert len(s["does"]) <= 320, (where, s["key"])   # 한두 줄 — 길어지면 사양서로


def _spec_exists(where, spec):
    file, at = spec
    text = (ROOT / "spec" / file).read_text(encoding="utf-8")   # 없는 사양서면 여기서 떨어진다
    for n in re.findall(r"§(\d+)", at):
        assert re.search(rf"^#{{3,4}} {n}[.\-]", text, re.M), f"{where}: {file} 에 §{n} 이 없음"


def test_modules_agents_common_and_specs_exist():
    for where, s in W.steps():
        for m in s["modules"]:
            assert W.module_path(m), f"{where} · {s['key']}: 없는 모듈 {m}"
        for a in s["agents"]:
            assert a in agents.BY_ID, f"{where} · {s['key']}: 등록 안 된 에이전트 {a}"
        if s["agents"]:
            assert "llm" in s["by"], f"{where} · {s['key']}: 에이전트가 도는 단계는 by 에 llm"
        for u in s["uses"]:
            assert u in W.BY_COMMON, f"{where} · {s['key']}: 없는 공통 모듈 {u}"
        if s["spec"]:
            _spec_exists(f"{where} · {s['key']}", s["spec"])


def test_every_task_has_entry_checks_and_step_conditions():
    """TASK 문서(② §10) — 시작 점검(시작할 때 저절로 확인하는 것)과 단계마다 조건. TASK 를 더하고 시작 점검을 빠뜨리거나, 단계를 더하고 「하려면 · 끝난 것으로 보는 때」 를 안 적으면 떨어진다."""
    whens = [w for w, _, _ in W.WHEN]
    assert whens == ["start", "upload", "enter", "manual"] and [k for k, _ in W.COND] == ["need", "done", "stop", "left"]
    for t in W.TASKS:
        items = t.get("entry") or ()
        if t.get("soon"):
            assert not items and W.entry(t) == [], f"{t['job']}: 준비 중인 TASK 에는 시작 점검이 없다"
            continue
        keys = [c["key"] for c in items]
        assert len(keys) == len(set(keys)), f"{t['job']}: 시작 점검 key 가 겹침"
        assert {"start", "upload", "enter"} <= {c["when"] for c in items}, f"{t['job']}: 시작할 때 · 올릴 때 · 화면을 열 때의 점검이 하나씩은 있어야 한다"
        assert [c for _, _, _, group in W.entry(t) for c in group] == sorted(items, key=lambda c: whens.index(c["when"])), t["job"]   # 때마다 묶어도 차례는 적은 그대로
        for c in items:
            where = f"task:{t['job']} · 시작 점검 {c['key']}"
            assert c["when"] in whens and c["name"] and c["does"] and c["by"] and set(c["by"]) <= set(W.BY), where
            assert len(c["does"]) <= 320 and len(c["miss"]) <= 320, where   # 한두 줄 — 길어지면 사양서로
            assert all(u in W.BY_COMMON for u in c["uses"]), where
            if c["when"] == "manual":
                assert "llm" in c["by"], f"{where}: 저절로 돌지 않는 것은 사람이 돌리는 LLM 이다"
            if c["spec"]:
                _spec_exists(where, c["spec"])
        for g in t["stages"]:
            for s in g["steps"]:
                where = f"task:{t['job']} · {s['key']}"
                assert s["soon"] or (s["need"] and s["done"]), f"{where}: 단계마다 「하려면」 · 「끝난 것으로 보는 때」 를 적는다"
                assert all(len(s[k]) <= 320 for k, _ in W.COND), where


def test_task_docs_are_the_registry_written_out():
    """tasks/<TASK 키>.md = 등록부에서 만든 TASK 문서(② §10 — workflow.md 가 전체 지도라면 이것은 그 TASK 의 세부). 등록부를 고치고 다시 만들지 않으면 떨어진다:
    python -X utf8 tools/workflow_md.py"""
    docs = W.task_docs()
    assert set(docs) == {W.TASK_DIR / f"{t['job']}.md" for t in W.TASKS} and W.TASK_DIR == ROOT / "tasks"
    assert set(W.TASK_DIR.glob("*.md")) == set(docs), "tasks/ 에 등록부에 없는 TASK 의 문서가 있다 — 지운다"
    for path, want in docs.items():
        assert path.is_file() and path.read_text(encoding="utf-8") == want, f"{path.name} 이 등록부와 다르다 — python -X utf8 tools/workflow_md.py 로 다시 만든다"
    cat = W.catalog()[0]
    for t in W.TASKS:
        md = docs[W.task_md(t["job"])]
        assert md.startswith(f"# {cat[t['job']]['name']} — `{t['job']}`") and t["inputs"] in md and t["output"] in md
        assert ("## 시작 점검" in md and "## 단계마다 조건" in md) != bool(t.get("soon")), t["job"]
        for g in t["stages"]:   # 그 TASK 의 workflow.md 절을 그대로 담는다(작업 진행 에이전트가 이 글을 그 TASK 의 절로 읽는다) + 조건
            for s in g["steps"]:
                assert s["name"] in md and s["does"] in md and all(s[k] in md for k, _ in W.COND), (t["job"], s["key"])
        for c in t.get("entry") or ():
            assert c["name"] in md and c["does"] in md and c["miss"] in md, (t["job"], c["key"])
    relay = docs[W.task_md("plan_to_report")]
    assert "### TASK 를 시작할 때" in relay and "### 저절로 돌지 않는 것" in relay and "  - 안 맞으면: " in relay and "  - 끝난 것으로 보는 때: " in relay and "## 쓰는 공통 모듈" in relay
    assert "에이전트: 09 자리 연결 검토" in relay and "`jobs/plan_to_report.md`" in relay and "#### " not in relay   # 묶음은 ### (workflow.md 의 #### 보다 한 층 위 — 문서 하나가 TASK 하나)
    wf = W.markdown()   # 전체 지도는 TASK 문서를 가리키기만 한다(머리에 — 첫 화면 에이전트가 머리만 읽는다)
    head = wf.split("### 사업계획서 양식 표준화 — `plan_fit`", 1)[1].split("\n#### ", 1)[0]
    assert "- 세부(TASK 문서 — 시작 점검 · 단계마다 조건): `tasks/plan_fit.md`" in head and "- 시작 점검(시작할 때 저절로 확인하는 것): TASK 를 시작할 때 — 문서 형식 · 목적 문서" in head
    assert "  - 끝난 것으로 보는 때: " not in wf and "tasks/report_merge.md" in wf


def test_every_registered_agent_is_placed_in_some_step():
    """새 LLM 호출(에이전트)을 만들면 그것이 도는 단계에 적는다 — 어느 과정에서 도는지 페이지에 보이게."""
    placed = {a for _, s in W.steps() for a in s["agents"]}
    assert set(agents.BY_ID) - placed == set()


def test_listing_adds_module_docs_agent_numbers_and_users_of_common_modules():
    L = W.listing()
    assert [t["job"] for t in L["tasks"]] == CATALOG_JOBS and L["by"] == W.BY and L["change"] == W.CHANGE
    by = {t["job"]: t for t in L["tasks"]}
    assert by["plan_to_report"]["prompt"] == "jobs/plan_to_report.md" and by["plan_fit"]["prompt"] is None and by["report_merge"]["soon"] and by["report_merge"]["stages"] == []
    link = next(s for g in by["plan_to_report"]["stages"] for s in g["steps"] if s["key"] == "llm")
    a = link["agents"][0]
    assert a["id"] == "merge_links" and a["no"] == "09" and a["name"] == "자리 연결 검토" and a["role"] and a["model"]["id"] and a["run"] == "눌러야 돎"
    assert link["optional"] and link["by"] == ["llm"] and link["spec"] == {"file": "spec/spec_병합.md", "at": "② §4"}
    mods = {m["name"]: m for m in link["modules"]}
    assert mods["merge_llm"]["path"] == "app/merge_llm.py" and mods["merge_llm"]["doc"].startswith("병합")
    common = {c["id"]: c for c in L["common"]}
    assert common["headings"]["usedBy"] == ["plan_fit", "plan_merge", "plan_to_report", "style_copy"] and "plan_fit" in common["division"]["usedBy"]   # 양식 표준화 2 · 3단계가 헤딩 추출을 쓴다(spec_양식표준화 ② §1) and common["verify"]["usedBy"] == []
    places = next(s for s in common["division"]["steps"] if s["key"] == "places")
    assert {m["name"]: m["path"] for m in places["modules"]}["division_profiles"] == "app/division_profiles/"   # 묶음(폴더) 모듈
    # TASK 문서(② §10) — 시작 점검은 때마다 묶어, 단계의 조건은 적힌 것만
    assert by["plan_fit"]["doc"] == "tasks/plan_fit.md" and by["report_merge"]["entry"] == [] and by["report_merge"]["doc"] == "tasks/report_merge.md"
    groups = by["plan_to_report"]["entry"]
    assert [g["when"] for g in groups] == ["start", "upload", "enter", "manual"] and groups[0]["name"] == "TASK 를 시작할 때" and groups[0]["note"]
    item = next(c for c in groups[2]["items"] if c["key"] == "slots")
    assert item["name"] == "두 문서가 있는가" and item["by"] == ["script"] and item["does"] and item["miss"] and item["spec"] == {"file": "spec/spec_작업.md", "at": "② §11·§17"}
    assert [c["key"] for c in link["cond"]] == ["need", "done", "left"] and link["cond"][1]["name"] == "끝난 것으로 보는 때" and places["cond"] == []


def test_workflow_md_is_the_registry_written_out():
    """저장소 루트의 workflow.md = 등록부에서 만든 글(② §8 — 에이전트가 늘 지니고 참조하는 지도). 등록부 · TASK 이름 · 에이전트 번호·이름 · jobs/ 를 고치고 다시 만들지 않으면 떨어진다:
    python -X utf8 tools/workflow_md.py"""
    md = W.markdown()
    assert W.MD == ROOT / "workflow.md" and W.MD.is_file(), "workflow.md 가 없다 — python -X utf8 tools/workflow_md.py"
    assert W.MD.read_text(encoding="utf-8") == md, "workflow.md 가 등록부와 다르다 — python -X utf8 tools/workflow_md.py 로 다시 만든다"
    cat, meta = W.catalog()
    assert list(cat) == CATALOG_JOBS and set(meta) == STAGE_META and all(v["name"] and v["desc"] for v in cat.values())
    assert all(f"— `{t['job']}`" in md for t in W.TASKS) and all(f"— `{c['id']}`" in md for c in W.COMMON)
    for where, s in W.steps():
        assert s["name"] in md and s["does"] in md, (where, s["key"])
    assert "에이전트: 09 자리 연결 검토" in md and "`jobs/plan_to_report.md`" in md and "1단계 문서 검토 › 2단계 구성 맞추기 › 3단계 내용 넣기 › 4단계 문서 정리" in md
    assert "1단계 프로젝트 구성 › 2단계 문서 프레임 작성 › 3단계 내용 매핑" in md and "2단계 문서 프레임 작성 › 3단계 내용 매핑 › 4단계" not in md   # 취합은 그대로 · 이관의 옛 묶음 이름은 없다


def test_api_and_page():
    c = TestClient(server.app)
    r = c.get("/api/workflow")
    assert r.status_code == 200 and r.json() == W.listing()
    p = c.get("/workflow")
    assert p.status_code == 200 and "text/html" in p.headers["content-type"] and p.headers["cache-control"] == "no-cache"
    for name in ("style.css", "workflow.css", "task_catalog.js", "workflow.js"):
        m = re.search(rf'"/static/{re.escape(name)}\?v=(\d+)"', p.text)
        assert m and int(m.group(1)) == int((server.STATIC / name).stat().st_mtime), name
        assert c.get(f"/static/{name}").status_code == 200
    assert 'id="wfNav"' in p.text and 'id="wfMain"' in p.text


def test_start_page_links_to_the_workflow_page_in_a_new_tab():
    html = TestClient(server.app).get("/").text
    m = re.search(r'<a class="btn wf-link" id="workflowLink" href="/workflow" target="_blank"[^>]*>', html)
    assert m and 'aria-label="TASK 워크플로우"' in m.group(0)
    assert html.index('id="workflowLink"') < html.index('id="agentBtn"')   # 에이전트 아이콘 앞(2026-11-18 — 전의 「에이전트 설정」 링크 자리 · smoke_agents_ui)
