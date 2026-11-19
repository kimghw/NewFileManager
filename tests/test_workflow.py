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
_TASK_BLOCK = re.search(r"const TASK_CATALOG = \(\{.*?\n(.*?)\n\}\);", CATALOG, re.S)[1]   # 붙박이 TASK 줄들(조립한 TASK 를 더하는 함수 앞까지)


def _catalog_docs():
    """task_catalog.js 의 TASK 마다 문서 칸 → {job: {files, gather, target, file}} — 등록부 roles 의 kind 를 견줄 원본(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」)."""
    heads = list(re.finditer(r'^  (\w+): \{ name: "', _TASK_BLOCK, re.M))
    out = {}
    for i, m in enumerate(heads):
        seg = _TASK_BLOCK[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(_TASK_BLOCK)]
        files, gather = re.search(r"\bfiles: \[([^\]]*)\]", seg), re.search(r'\bgather: \{ base: "(\w*)", parts: "(\w*)" \}', seg)
        target, file = re.search(r'\btarget: "(\w*)"', seg), re.search(r'\bfile: "(\w*)"', seg)
        out[m[1]] = {"files": re.findall(r'"(\w+)"', files[1]) if files else [], "gather": {"base": gather[1], "parts": gather[2]} if gather else None,
                     "target": target[1] if target else None, "file": file[1] if file else ""}
    return out


def test_catalog_is_read_the_way_this_test_expects():
    assert CATALOG_JOBS[:2] == ["plan_fit", "plan_merge"] and "report_merge" in CATALOG_SOON and STAGE_META >= {"config", "frame", "map", "clean"}
    docs = _catalog_docs()
    assert list(docs) == CATALOG_JOBS and docs["plan_to_report"]["files"] == ["plan", "report"] and docs["plan_merge"]["gather"] == {"base": "plan", "parts": "part"} and docs["plan_fit"]["file"] == "plan"


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
    keys = {g["id"]: [s["key"] for s in g["steps"] if not s["optional"]] for g in relay}   # 선택 단계를 뺀 차례 — 화면의 TASK_STAGES.keys(app.js)와 같다(헤딩 · 표의 LLM 검증·보완은 제 줄이 있는 단계다 — §21)
    assert keys == {"review": ["files", "heads", "headsLlm"], "frame": ["config", "division", "reheads", "reheadsLlm"], "map": ["link", "plan", "apply", "later"], "clean": ["guide"]}
    assert [s["key"] for g in relay for s in g["steps"] if s["optional"]] == ["configLoad", "llm", "tableMap", "gaps"]   # 구성 불러오기(선택) · 3단계의 LLM 검토들
    # 단계 모듈(spec_워크플로우 ② §13 — 2026-11-19 사용자 "각 단계를 , 여기 모듈로 두고,, task 모듈로 조립할 수 있도록"): 이관의 묶음 넷 = 단계 모듈 넷을 조립한 것
    mods = {c["id"]: c for c in W.COMMON if c.get("kind") == "stage"}
    assert [m[0] for m in W.STAGE_MODULES] == list(mods) == [c["id"] for c in W.COMMON[:4]] == ["stage_review", "stage_fit", "stage_fill", "stage_clean"]   # 공통 모듈 목록의 맨 앞 넷
    assert [g["module"] for g in relay] == list(mods) and all(W.assembled(m) == ["plan_to_report"] for m in mods)
    for g in relay:   # 묶음의 단계 = (그 TASK 만의 앞 단계 — 이관의 「준비」) + 모듈의 단계: key · 이름이 같고 글은 문서 이름만 다르다
        own, mk = list(g["steps"]), list(mods[g["module"]]["steps"])
        own = own[len(own) - len(mk):]
        assert [x["key"] for x in own] == [x["key"] for x in mk] and [x["name"] for x in own] == [x["name"] for x in mk] and g["name"] == mods[g["module"]]["name"], g["id"]
        assert all(x["does"].replace("사업계획서", "원본 문서").replace("연차보고서", "목적 문서") == y["does"] for x, y in zip(own, mk)), g["id"]
    assert all(g.get("module") is None for t in W.TASKS if t["job"] != "plan_to_report" for g in t["stages"])   # 다른 TASK 는 아직 조립하지 않았다(제 묶음 그대로)
    assert [g["id"] for g in W.BY_JOB["plan_merge"]["stages"]] == ["config", "frame", "map"]                # 취합 = 1~3단계
    ids = [c["id"] for c in W.COMMON]
    assert len(ids) == len(set(ids)) and all(c["name"] and c["does"] and c["where"] and c["steps"] for c in W.COMMON)
    for where, s in W.steps():
        assert s["name"] and s["does"] and s["by"] and set(s["by"]) <= set(W.BY) and s["change"] in W.CHANGE, (where, s["key"])
        assert len(s["does"]) <= 320, (where, s["key"])   # 한두 줄 — 길어지면 사양서로


# 붙박이 둘의 하는 문서 — spec_워크플로우 ② §15 「문서마다 단위문서 TASK」 의 표 그대로(근거 = 실행 코드: 이관 app.js taskSteps · taskRunSteps / 취합 gather.js · merge_gather_api)
ON_TABLE = {
    "plan_to_report": {"files": "both", "heads": "both", "headsLlm": "source", "configLoad": "source", "config": "source", "division": "target", "reheads": "target", "reheadsLlm": "target",
                       **dict.fromkeys(("link", "llm", "plan", "tableMap", "gaps", "apply", "later"), "pair"), "guide": "target"},
    "plan_merge": {"files": "target", "config": "target", "division": "target", "frame": "target", "hand": "target", "part": "source", "heads": "source",
                   **dict.fromkeys(("link", "llm", "plan", "apply", "drop"), "pair")},
}


def test_document_roles_and_what_each_step_works_on():
    """문서마다 단위문서 TASK(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」 — 2026-11-19 사용자 "목적문서랑 원본문서에 대해서 각각 task 를 할당할 수 있도록 해줘"):
    워크플로우의 문서 역할(roles — 원본 → 목적) · 단계의 하는 문서(on). 문서 여럿인 워크플로우의 단계는 모두 on 이 있고, 문서 하나인 워크플로우 · 공통 모듈의 단계는 비어 있다.
    roles 의 kind 는 화면(task_catalog.js)의 문서 칸(files · gather · target · file)과 같다."""
    docs = _catalog_docs()
    for t in W.TASKS:
        rs, k = t["roles"], docs[t["job"]]
        assert [r["role"] for r in rs] in (["target"], ["source", "target"]) and all(r["name"] and isinstance(r["many"], bool) for r in rs), t["job"]
        multi, by = len(rs) == 2, {r["role"]: r for r in rs}
        for g in t["stages"]:
            for s in g["steps"]:
                assert (s["on"] in W.ON) if multi else s["on"] == "", (t["job"], s["key"], s["on"])
        assert by["target"]["kind"] == (k["target"] or k["file"]) and not by["target"]["many"], t["job"]   # 목적 문서 = 카탈로그의 target(없으면 그 TASK 의 문서 file) — 늘 하나
        if k["files"]:   # 이관형 — 문서 칸 = [원본, 목적]
            assert [r["kind"] for r in rs] == k["files"] and k["target"] == k["files"][1] and not by["source"]["many"], t["job"]
        elif k["gather"]:   # 취합 — 취합본 + 기관 문서 여럿
            assert (by["source"]["kind"], by["source"]["many"], by["target"]["kind"]) == (k["gather"]["parts"], True, k["gather"]["base"]), t["job"]
        elif t.get("soon"):   # 준비 중인 취합형(연차보고서 취합) — 카탈로그에 기관 문서 칸이 아직 없다
            assert (by["source"]["kind"], by["source"]["many"]) == ("part", True) and not t["stages"], t["job"]
        else:
            assert not multi, t["job"]   # 문서 하나 — 그 문서가 목적 문서
    for job, want in ON_TABLE.items():
        assert {s["key"]: s["on"] for g in W.BY_JOB[job]["stages"] for s in g["steps"]} == want, job
    assert all(s["on"] == "" for c in W.COMMON for s in c["steps"])   # 공통 모듈(단계 절 포함)의 단계는 하는 문서를 적지 않는다 — 그 단계를 조립한 워크플로우에만
    assert [r["name"] for r in W.BY_JOB["plan_to_report"]["roles"]] == ["사업계획서", "연차보고서"] and [r["name"] for r in W.BY_JOB["plan_merge"]["roles"]] == ["기관 문서", "취합본"]   # 「취합 대상」 이라 하지 않는다
    assert W.on_label("pair") == "원본 → 목적" and W.on_label("pair", many=True) == "원본 문서마다 → 목적" and W.on_label("target", many=True) == "목적 문서" and W.on_label("") == ""


def test_unit_tasks_are_the_steps_that_touch_each_document():
    """문서마다의 단위문서 TASK = 그 역할의 문서에 닿는 단계(on 이 그 역할 · both · 목적 문서면 pair 도)를 묶음 차례로 — 닿는 단계가 있는 묶음만(② §15)."""
    keys = lambda t, role: [(g["id"], [s["key"] for s in hit]) for g, hit in W.unit(t, role)]  # noqa: E731
    relay, gather, fit = W.BY_JOB["plan_to_report"], W.BY_JOB["plan_merge"], W.BY_JOB["plan_fit"]
    assert keys(relay, "source") == [("review", ["files", "heads", "headsLlm"]), ("frame", ["configLoad", "config"])]   # 원본 문서 = 문서 검토 + 구성의 기준(문서는 안 바뀜)
    assert keys(relay, "target") == [("review", ["files", "heads"]), ("frame", ["division", "reheads", "reheadsLlm"]),
                                     ("map", ["link", "llm", "plan", "tableMap", "gaps", "apply", "later"]), ("clean", ["guide"])]   # 내용 넣기는 원본 → 목적(목적 문서가 받음)
    assert keys(gather, "source") == [("map", ["part", "heads"])]   # 기관 문서마다(여럿)
    assert keys(gather, "target") == [("config", ["files", "config"]), ("frame", ["division", "frame", "hand"]), ("map", ["link", "llm", "plan", "apply", "drop"])]
    assert keys(fit, "target") == [(g["id"], [s["key"] for s in g["steps"]]) for g in fit["stages"]] and keys(fit, "source") == []   # 문서 하나 — 그 워크플로우가 곧 그 문서의 단위문서 TASK
    assert keys(W.BY_JOB["report_merge"], "source") == keys(W.BY_JOB["report_merge"], "target") == []   # 준비 중 — 단계가 없다
    for t in W.TASKS:   # 모든 단계가 어느 문서의 단위문서 TASK 에든 든다(빠지는 단계 없음)
        hit = {s["key"] for r in t["roles"] for _, ss in W.unit(t, r["role"]) for s in ss}
        assert hit == {s["key"] for g in t["stages"] for s in g["steps"]}, t["job"]


def test_review_module_follows_the_documents_it_is_given():
    """「문서 검토」 단계 모듈의 선택지(② §15 — 조립한 워크플로우가 문서마다 고른 대로): 기본 = 붙박이 이관과 같은 글 · 헤딩 · 표 분석 = 고른 문서 ·
    LLM 검증·보완 = 원본(골랐으면) + 목적(골랐고 「구성 맞추기」 가 없으면) · 닿는 문서가 없는 단계는 서지 않고, 글에는 그 단계를 하는 문서의 이름만 든다."""
    S, D = "가문서", "나문서"
    assert W._st_review(S, D) == W._st_review(S, D, src=True, dst=True, dst_llm=False)
    want = {(True, True, False): [("heads", "both"), ("headsLlm", "source")], (True, False, False): [("heads", "source"), ("headsLlm", "source")],
            (False, True, False): [("heads", "target")], (False, True, True): [("heads", "target"), ("headsLlm", "target")],
            (True, True, True): [("heads", "both"), ("headsLlm", "both")], (False, False, True): []}
    for (src, dst, dst_llm), steps in want.items():
        got = W._st_review(S, D, src=src, dst=dst, dst_llm=dst_llm)
        assert [(s["key"], s["on"]) for s in got] == steps, (src, dst, dst_llm)
        for s in got:
            text = " ".join(s[k] for k in ("does", "out", "need", "done", "left"))
            if s["on"] == "source":   # 원본 문서만의 단계 — 목적 문서의 이름은 기본 글(「다시 문서 검토(LLM)」 를 가리킴)에만
                assert S in text and (D not in text or (dst and not dst_llm and s["key"] == "headsLlm")), (src, dst, s["key"])
            if s["on"] == "target":
                assert D in text and S not in text, (src, dst, s["key"])
            assert ("작성 지침" in s["out"]) == (s["key"] == "heads" and dst), (src, dst, s["key"])   # 작성 지침 저장은 양식(목적 문서)의 일 — 목적 문서가 검토할 때만


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
    assert "### TASK 를 시작할 때" in relay and "### 저절로 돌지 않는 것" in relay and "  - 안 맞으면: " in relay and "  - 끝난 것으로 보는 때: " in relay and "## 쓰는 도구" in relay and "공통 모듈" not in relay   # 화면 말 「도구」(2026-11-19 사용자 "모듈이라고 하지 말고 공통 모듈을 도구라고 하자")
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


def test_listing_carries_roles_with_unit_tasks_and_step_documents():
    """GET /api/workflow(② §15 「문서마다 단위문서 TASK」): 워크플로우마다 roles[{role, name, kind, many, unit[{stage, steps}]}](원본 → 목적) · 단계마다 on — 등록부 · unit() 과 같다."""
    L = W.listing()
    by = {t["job"]: t for t in L["tasks"]}
    for t in W.TASKS:
        assert by[t["job"]]["roles"] == [{"role": r["role"], "name": r["name"], "kind": r["kind"], "many": r["many"],
                                          "unit": [{"stage": g["id"], "steps": [s["key"] for s in hit]} for g, hit in W.unit(t, r["role"])]} for r in t["roles"]], t["job"]
        assert [s["on"] for g in by[t["job"]]["stages"] for s in g["steps"]] == [s["on"] for g in t["stages"] for s in g["steps"]], t["job"]
    assert by["plan_to_report"]["roles"][0] == {"role": "source", "name": "사업계획서", "kind": "plan", "many": False,
                                                "unit": [{"stage": "review", "steps": ["files", "heads", "headsLlm"]}, {"stage": "frame", "steps": ["configLoad", "config"]}]}
    assert by["plan_fit"]["roles"] == [{"role": "target", "name": "사업계획서", "kind": "plan", "many": False,
                                        "unit": [{"stage": g["id"], "steps": [s["key"] for s in g["steps"]]} for g in W.BY_JOB["plan_fit"]["stages"]]}]
    assert by["report_merge"]["roles"] == [{"role": "source", "name": "기관 문서", "kind": "part", "many": True, "unit": []},
                                           {"role": "target", "name": "연차보고서(취합본)", "kind": "report", "many": False, "unit": []}]
    assert all(s["on"] == "" for c in L["common"] for s in c["steps"]) and all("on" in s for t in L["tasks"] for g in t["stages"] for s in g["steps"])


def test_written_out_docs_show_unit_tasks_and_step_documents():
    """만든 글(workflow.md · TASK 문서 — ② §15): 문서 여럿인 TASK 의 머리에 「문서마다 단위문서 TASK」 한 줄(원본 문서(이름): 묶음(단계 …) › … / 목적 문서(이름): …) ·
    단계 줄 끝에 하는 문서. 문서 하나인 TASK 는 그 줄 · 표지가 없다(그 TASK 가 곧 그 문서의 단위문서 TASK)."""
    wf = W.markdown()
    head = lambda title: wf.split(title, 1)[1].split("\n#### ", 1)[0]  # noqa: E731 — TASK 머리(첫 단계 묶음 앞 — 첫 화면 에이전트가 읽는 곳)
    relay, gather, fit = head("### 사업계획서 → 연차보고서 이관 — `plan_to_report`"), head("### 사업계획서 취합 — `plan_merge`"), head("### 사업계획서 양식 표준화 — `plan_fit`")
    assert ("- 문서마다 단위문서 TASK — 원본 문서(사업계획서): 1단계 문서 검토(「준비」 · 「헤딩 · 표 분석」 · 「LLM 검증·보완」) › 2단계 구성 맞추기(「구성 불러오기」 · 「프로젝트 구성 확정」)"
            " / 목적 문서(연차보고서): 1단계 문서 검토(「준비」 · 「헤딩 · 표 분석」) › 2단계 구성 맞추기(「프로젝트 구성 반영」 · 「다시 문서 검토」 · 「다시 문서 검토(LLM)」)") in relay
    assert "› 3단계 내용 넣기(← 원본 문서: 「자리 연결」 · 「자리 연결 LLM 검토」 · " in relay and "› 4단계 문서 정리(「작성요령 삭제」)\n- 알아 둘 것: " in relay   # 산출물 다음 · 알아 둘 것 앞의 한 줄
    assert ("- 문서마다 단위문서 TASK — 원본 문서(기관 문서 — 문서마다): 3단계 내용 매핑(「기관 문서 올리기 · 반영할 기관 지정」 · 「헤딩 · 표 분석」)"
            " / 목적 문서(취합본): 1단계 프로젝트 구성(「준비」 · 「프로젝트 구성 확정」)") in gather and "3단계 내용 매핑(← 원본 문서마다: 「자리 연결 · 기관 작성 내용 판정」" in gather
    assert "단위문서 TASK" not in fit and "단위문서 TASK" not in head("### 연차보고서 취합 — `report_merge` (준비 중)")   # 문서 하나 · 단계 없는 준비 중
    assert "- **② 자리 연결** — 스크립트 · 저장만 · 필수 · 원본 → 목적. " in wf and "- **LLM 검증·보완** — 사람 → LLM · 저장만 · 필수 · 원본 문서. " in wf   # 단계 줄 끝에 하는 문서
    assert "- **헤딩 · 표 분석** — 스크립트 · 저장만 · 필수 · 두 문서. " in wf and "- **기관 문서 올리기 · 반영할 기관 지정** — 사람 · 저장만 · 필수 · 원본 문서마다. " in wf
    assert "- **⑥ 작성요령 삭제** — 스크립트 → 사람 · 문서 바뀜 · 필수 · 목적 문서. " in wf and "- **헤딩 · 템플릿 추출** — 스크립트 · 저장만 · 자동. " in wf   # 문서 하나인 TASK 는 표지 없음
    doc, one = W.task_markdown("plan_to_report"), W.task_markdown("plan_fit")
    assert "- 문서마다 단위문서 TASK — 원본 문서(사업계획서): " in doc and "· 하는 문서. 하는 일`" in doc and "하는 문서" not in one and "단위문서 TASK" not in one


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
