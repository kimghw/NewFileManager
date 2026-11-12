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
            payload = {"kind": "rnd", "job": job, "file": role, "project": ""}
            response = client.put(f"/api/works/{wid}/task", json=payload)
            assert response.status_code == 200, (job, role, response.text)
            assert response.json()["task"] == payload
            assert works.work(wid)["task"] == payload


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


def test_catalog_cards_have_readable_labels_and_matching_logos(catalog):
    """새 TASK의 이름·행동·로고 누락으로 빈 시작 카드가 생기지 않게 한다."""
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    for job, task in catalog.items():
        for field in ("name", "act", "doc", "up", "desc"):
            assert isinstance(task.get(field), str) and task[field].strip(), (job, field)
        assert f'id="taskIcon-{job}"' in html, job
        assert task["file"] in server.TASK["file"], job
