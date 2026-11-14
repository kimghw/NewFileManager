"""TASK 카탈로그와 저장 API의 계약 — 카드가 여는 TASK/문서 역할을 서버도 받는지.

화면 정의는 Node의 격리된 컨텍스트로 읽는다. 문서 분석·LLM·사용자 작업은 쓰지 않는다.
"""
import json
from pathlib import Path
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from app import server, works


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def catalog():
    node = shutil.which("node")
    if not node:
        pytest.skip("TASK JavaScript 계약 검사에는 Node.js가 필요합니다")
    result = subprocess.run(
        [node, "-e", "const fs = require('node:fs'), vm = require('node:vm'); "
         "const source = fs.readFileSync(process.argv[1], 'utf8'); "
         "process.stdout.write(vm.runInNewContext(source + '\\nJSON.stringify(TASK_CATALOG)', {}, {timeout: 1000}));",
         str(ROOT / "app" / "static" / "task_catalog.js")],
        capture_output=True, text=True, encoding="utf-8", check=True, timeout=10,
    )
    return json.loads(result.stdout)


def test_catalog_tasks_and_document_roles_are_accepted_by_the_save_api(catalog):
    """새 카드를 추가하고 서버 허용 목록을 빠뜨려 저장에 실패하는 회귀를 잡는다."""
    assert set(catalog) == set(server.TASK["job"]) - {""}
    client = TestClient(server.app)
    for index, (job, task) in enumerate(catalog.items(), 1):
        wid = f"{index:012x}"
        works.create(wid, "catalog.hwpx", "hwpx", b"catalog contract")
        roles = [task["file"], *task.get("files", []), *task.get("gather", {}).values()]
        for role in dict.fromkeys(roles):
            payload = {"kind": task.get("kind", "rnd"), "job": job, "file": role, "project": ""}   # 작업 종류는 카탈로그의 것(없으면 연구개발 — 「문서 일반 편집」 만 general)
            response = client.put(f"/api/works/{wid}/task", json=payload)
            assert response.status_code == 200, (job, role, response.text)
            assert response.json()["task"] == payload
            assert works.work(wid)["task"] == payload


def test_task_kind_follows_the_job(catalog):
    """할 일과 작업 종류의 조합(spec_일반편집 ② §11): 카탈로그의 kind 가 서버 표(TASK_KIND)와 같고, 어긋난 조합은 저장하지 않는다 — 연구개발의 할 일은 작업 종류를 비운 채로도 되고(전과 같음),
    작업 종류가 정해진 할 일(문서 일반 편집)은 비워도 안 된다(비우면 화면·프로젝트 구분 기준 공유가 연구개발로 본다 — 2026-11-13 astra 결과 검토)."""
    assert {job: task["kind"] for job, task in catalog.items() if task.get("kind", "rnd") != "rnd"} == server.TASK_KIND
    assert set(server.TASK_KIND.values()) <= set(server.TASK["kind"])
    client = TestClient(server.app)
    wid = "0000000000ff"
    works.create(wid, "kind.hwpx", "hwpx", b"kind contract")
    for job in catalog:
        own = server.TASK_KIND.get(job, "rnd")
        other = "general" if own == "rnd" else "rnd"
        assert client.put(f"/api/works/{wid}/task", json={"kind": other, "job": job, "file": "", "project": ""}).status_code == 400, job
        assert client.put(f"/api/works/{wid}/task", json={"kind": "", "job": job, "file": "", "project": ""}).status_code == (200 if own == "rnd" else 400), job
    assert client.put(f"/api/works/{wid}/task", json={"kind": "general", "job": "", "file": "", "project": ""}).status_code == 200   # TASK 없는 일반 문서


def test_catalog_keeps_the_source_and_destination_roles(catalog):
    """입력 방향이 바뀌면 다른 문서의 내용을 바꾸므로 역할 계약을 고정한다."""
    assert catalog["plan_fit"]["file"] == "plan"
    assert catalog["report_fit"]["file"] == "report"
    assert catalog["plan_to_report"]["files"] == ["plan", "report"]
    assert catalog["plan_merge"]["gather"] == {"base": "plan", "parts": "part"}
    assert catalog["report_merge"]["soon"] is True
    assert not catalog["report_merge"].get("files")
    assert not catalog["report_merge"].get("gather")
    for job, task in catalog.items():
        assert not (task.get("files") and task.get("gather")), job


def test_catalog_target_roles_match_the_server(catalog):
    """화면의 목적 문서 표시(target)가 서버의 목적 문서(works.TARGET_FILE — 보이는 이름)와 갈라지지 않게 한다(spec_작업 ② §10 「목적 문서 표시」)."""
    assert {job: task["target"] for job, task in catalog.items() if task.get("target")} == works.TARGET_FILE
    for job, task in catalog.items():
        if task.get("target"):
            roles = [task["file"], *task.get("files", []), *task.get("gather", {}).values()]
            assert task["target"] in roles and len(set(roles) - {""}) >= 2, job  # 목적 문서 말고 원본 종류가 하나 이상


def test_frame_name_tasks_match_the_catalog(catalog):
    """프레임 이름(spec_작업 ② §10 「프레임 이름」)을 쓰는 TASK(works.FRAME_FILE)가 카탈로그에서 그 종류의 문서 하나를 맞추는 TASK 이고(목적·원본이 갈리는 TASK 가 아님),
    이름에 넣는 첨부 파일 종류의 말(works.FILE_LABEL)이 화면의 말(app.js WORK_TASK.file)과 같다."""
    script = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    for job, kind in works.FRAME_FILE.items():
        assert catalog[job]["file"] == kind and not catalog[job].get("target") and not catalog[job].get("files") and not catalog[job].get("gather"), job
        assert f'["{kind}", "{works.FILE_LABEL[kind]}"]' in script, kind
    assert not set(works.FRAME_FILE) & set(works.TARGET_FILE)   # 목적 문서의 이름 규칙(올린 이름_프로젝트)과 겹치지 않는다


def test_catalog_cards_have_readable_labels_and_matching_logos(catalog):
    """새 TASK의 이름·행동·로고 누락으로 빈 시작 카드가 생기지 않게 한다."""
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    for job, task in catalog.items():
        for field in ("name", "act", "doc", "up", "desc"):
            assert isinstance(task.get(field), str) and task[field].strip(), (job, field)
        assert f'id="taskIcon-{job}"' in html, job
        assert task["file"] in server.TASK["file"], job
