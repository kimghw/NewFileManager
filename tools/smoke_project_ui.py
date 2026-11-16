"""프로젝트 → TASK → 라운드 통합 화면 검사. 실제 소형 HWPX + 격리 서버, PDF·LLM 끔.

    python -X utf8 tools/smoke_project_ui.py <출력 폴더> [--port 18230]

프로젝트/TASK별 참고 문서 격리, 작업 리스트 이동, 구분 기준 공유·이전 라운드 보관,
현재 수정본/원본 분기, 패널 키보드 탐색·320px 폭을 확인한다.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

import requests
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--port", type=int, default=18230)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
TMP = Path(tempfile.mkdtemp(prefix="srv-", dir=OUT))
env = {**os.environ, "PYTHONUTF8": "1", "NFM_PDF": "off", "NFM_LLM_BACKEND": "off",
       **{key: str(TMP / name) for key, name in {"NFM_WORKS": "works", "NFM_RENDER": "render", "NFM_HEADINGS": "headings",
          "NFM_FORMS": "forms", "NFM_DIVISION_PRESETS": "presets.json"}.items()}}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
BASE = f"http://127.0.0.1:{args.port}"
VALUES = {"stages": [2, 1], "orgs": {"lead": "주관 A", "joint": ["공동 B"]}}
CHANGED = {"stages": [1, 2], "orgs": {"lead": "주관 C", "joint": ["공동 D"]}}
errors, fails, llm_calls = [], [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:450] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def api(method, path, **kwargs):
    response = requests.request(method, BASE + path, timeout=120, **kwargs)
    response.raise_for_status()
    return response


def upload(role="plan", project="프로젝트 A", job="plan_to_report"):
    wid = api("POST", "/api/samples/" + quote("기술수요조사서.hwpx") + "?new=1").json()["docId"]
    api("PUT", f"/api/works/{wid}/task", json={"kind": "rnd", "file": role, "project": project, "job": job, "round": 1})
    return wid


def paragraphs(blocks):
    for block in blocks:
        if block["type"] == "paragraph":
            yield block
        for cell in block.get("cells", []):
            yield from paragraphs(cell.get("blocks", []))


def division(wid):
    return api("GET", f"/api/docs/{wid}/divisions").json()


def wait_work(page, wid):
    page.wait_for_function("id => state.id === id && !!document.querySelector('#doc .para') && !state.busy", arg=wid, timeout=120000)
    page.wait_for_function("() => document.getElementById('panel').dataset.tool === 'Div' && !!document.querySelector('.project-round-row') && !projectStarting", timeout=30000)


def show_list(page):
    """작업 리스트 열기 — 상단 바 아이콘 #taskListBtn(2026-11-16 패널 머리 탭에서 옮김). 누름은 켜고 끄기라 이미 보이면(눌림) 누르지 않는다"""
    if page.get_attribute("#taskListBtn", "aria-pressed") != "true":
        page.locator("#taskListBtn").click()
    page.wait_for_function("() => document.getElementById('panel').dataset.tool === 'Tasks'")


def select_work(page, wid):
    show_list(page)
    button = page.locator(f'[data-project-work="{wid}"]')
    previous = button.locator("xpath=ancestor::details[contains(@class, 'project-previous')]")
    if previous.count() and not previous.evaluate("e => e.open"):
        previous.locator(":scope > summary").click()
    button.click()
    wait_work(page, wid)


def new_round(page, wid, source):
    page.locator("#toolTabTask").click()
    wait_work(page, wid)
    page.locator('[data-new-round="1"]').click()
    page.locator("#projectRoundSource").select_option(source)
    with page.expect_response(lambda r: r.url.endswith(f"/api/works/{wid}/round") and r.request.method == "POST", timeout=120000) as response:
        page.locator("#projectRoundStart").click()
    check(f"{source} 라운드 API 성공", response.value.status == 200, response.value.status)
    result = response.value.json()
    wait_work(page, result["docId"])
    return result


SCOPE = """() => ({
  slots: Object.fromEntries([...document.querySelectorAll('#taskFlow select[data-task-file]')].map(e => [e.dataset.taskFile, e.value])),
  options: [...document.querySelectorAll('#taskFlow select[data-task-file]')].map(e => [...e.options].map(o => o.value).filter(Boolean)),
  documents: [...document.getElementById('docSwitch').options].map(o => o.value),
  peers: [...document.querySelectorAll('#peerTabs [data-peer-doc]')].map(e => e.dataset.peerDoc), shown: peerShown()
})"""


try:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if requests.get(BASE + "/api/works", timeout=1).status_code == 200:
                break
        except requests.RequestException:
            pass
        if proc.poll() is not None:
            raise RuntimeError("임시 서버 시작 실패 — server.log 확인")
        time.sleep(.2)
    else:
        raise RuntimeError("임시 서버 시작 시간 초과")

    plan, report = upload(), upload("report")
    other_task = upload(job="plan_fit")
    outside = upload(project="프로젝트 B")
    shared = api("PUT", f"/api/docs/{plan}/divisions/settings", json={"values": VALUES}).json()["settings"]
    check("같은 프로젝트의 다른 TASK도 구분 기준 공유", division(report)["settings"] == shared and division(other_task)["settings"] == shared)
    check("다른 프로젝트의 구분 기준은 독립", division(outside)["settings"] is None)
    para = next(b for b in paragraphs(api("GET", f"/api/docs/{report}").json()["blocks"]) if len(b.get("text", "").strip()) > 10)
    marker = " 프로젝트 라운드 수정 확인"
    edited = para["text"] + marker
    api("PATCH", f"/api/docs/{report}/blocks/{para['id']}", json={"text": edited})
    before = api("GET", f"/api/docs/{report}/download").content
    old_task = api("GET", "/api/works").json()
    old_task = {w["id"]: w["task"] for w in old_task}

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.add_init_script("try { localStorage.setItem('nfm.toolMore', '1'); } catch (e) {}")  # 패널 머리 오른쪽 묶음(검증·PDF·기록)을 펴 둔다 — 접힘은 smoke_panel_head_ui.py(2026-11-16)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("dialog", lambda dialog: dialog.accept())
        page.on("request", lambda request: llm_calls.append(request.url) if request.method == "POST" and any(k in request.url for k in ("/llm", "/extract", "/analyze")) else None)
        page.goto(BASE + "/#w=" + report)
        page.wait_for_function("id => state.id === id && !!document.querySelector('#doc .para') && worksList.length >= 4", arg=report, timeout=120000)
        page.locator("#toolTabTask").click()
        wait_work(page, report)
        fields = page.locator("#divBox .dv-task > .dv-task-field > span").all_text_contents()
        check("작업 내용 — 프로젝트가 먼저, TASK가 다음", fields[:2] == ["프로젝트", "TASK"], fields)
        check("현재 TASK와 Round 1 표시", page.locator('#divBox select[data-task="job"]').input_value() == "plan_to_report"
              and page.locator('.project-round-label select').input_value() == "1")
        check("구분 기준 프로젝트 공유 안내", "프로젝트 공유" in page.locator(".project-sharing").inner_text())
        page.wait_for_function("id => peerShown() === id", arg=plan, timeout=30000)
        scope = page.evaluate(SCOPE)
        check("첨부·참고 후보는 같은 프로젝트·TASK·라운드만", scope["slots"] == {"plan": plan, "report": report}
              and all(set(options) == {plan, report} for options in scope["options"]), scope)
        check("문서 선택과 둘째 면도 같은 작업 범위만", set(scope["documents"]) == {plan, report} and scope["peers"] == [plan] and scope["shown"] == plan, scope)

        # ---- 구분 기준의 있음/없음 줄 · 구분 기준 버전(spec_작업 ② §19) — 프로젝트 칸 아래 두 줄. 버전 추가 → 목록 → 적용(입력 + 확정) → 삭제, 모두 인라인(창 없음)
        SHARING = "() => { const e = document.querySelector('#divBox .project-sharing'); return { kind: e.dataset.division, text: e.innerText }; }"
        VERSION_OPTIONS = "() => [...document.querySelectorAll('select[data-division-version] option')].map(o => o.textContent)"
        sharing = page.evaluate(SHARING)
        check("구분 기준 있음 줄 — 표지 · 요약 · 프로젝트 공유", sharing["kind"] == "has" and "프로젝트 구성 있음" in sharing["text"] and "주관 주관 A" in sharing["text"] and "프로젝트 공유" in sharing["text"], sharing)
        check("버전 줄 — 처음엔 「저장된 버전 없음」 + 「버전 추가」", page.locator("#divBox .project-versions .project-versions-none").inner_text() == "저장된 버전 없음"
              and page.locator("[data-version-add]").is_enabled() and page.locator("select[data-division-version]").count() == 0)
        page.locator("[data-version-add]").click()
        version_name = page.locator("input[data-version-name]")
        check("버전 추가 — 인라인 이름 줄(기본값 = 당해 차년도 · 포커스)", version_name.input_value() == "1차년도" and page.evaluate("() => document.activeElement.dataset.versionName === '1'"))
        with page.expect_response(lambda r: r.url.endswith(f"/api/docs/{report}/divisions/versions") and r.request.method == "POST", timeout=30000) as version_saved:
            version_name.press("Enter")
        check("버전 저장 API 성공", version_saved.value.status == 200, version_saved.value.status)
        page.wait_for_selector("select[data-division-version]")
        versions = division(report).get("versions") or []
        vid = versions[0]["id"] if versions else ""
        options = page.evaluate(VERSION_OPTIONS)
        check("버전 목록 — 「이름 — 당해 N차년도 · 요약 · 지금」 · 서버에 하나(지금 입력과 같음) · 이름 줄 닫힘", len(versions) == 1 and versions[0]["name"] == "1차년도" and versions[0]["active"] is True
              and len(options) == 2 and options[0] == "버전 고르기" and options[1].startswith("1차년도 — 당해 1차년도 · 1단계(1–2차년도)") and options[1].endswith("· 지금")
              and page.locator("select[data-division-version]").input_value() == vid and page.locator("input[data-version-name]").count() == 0, (versions, options))
        check("상태 줄 꼬리표 「버전 「…」」 · 「구성 불러오기」 목록에는 버전이 없음(버전은 버전 줄에서만 — 적용은 확정까지 한다)", page.evaluate("() => (document.querySelector('#divPresetStatus [data-version-tag]') || {}).textContent || ''") == "버전 「1차년도」"
              and page.locator('#divSourceSel option[value^="version:"]').count() == 0 and page.locator("#divSourceSel option", has_text="버전 「").count() == 0)
        page.locator('#divBox input[data-task="project"]').click()
        page.wait_for_selector("#taskProjectList [role=option]")
        own = page.locator("#taskProjectList [role=option]").first.locator(".project-combo-tag").all_text_contents()
        check("프로젝트 고르기 목록의 지금 프로젝트 줄 — 구분 기준 있음 · 버전 1개 · 지금", own == ["프로젝트 구성 있음", "버전 1개", "지금"], own)
        page.screenshot(path=str(OUT / "00a_project_combo_versions.png"), clip={"x": 900, "y": 0, "width": 600, "height": 520})  # 고르기 목록(body 에 뜬다) + 있음 줄 + 버전 줄
        page.keyboard.press("Escape")
        page.locator("#panel").screenshot(path=str(OUT / "00b_division_versions.png"))
        page.locator("[data-version-add]").click()
        check("버전 추가를 다시 — 같은 이름(기본값)이면 이름 줄을 열 때부터 덮어씀 안내 · 단추 「덮어쓰기」", page.locator("#divBox .project-versions-note").inner_text() == "같은 이름 「1차년도」 을 덮어씁니다"
              and page.locator("[data-version-save]").inner_text() == "덮어쓰기")
        version_name.fill("2차년도")
        check("다른 이름을 적으면 안내가 사라지고 단추 「저장」", page.locator("[data-version-save]").inner_text() == "저장" and page.locator("#divBox .project-versions-note").text_content() == "")
        version_name.press("Escape")
        check("Esc — 이름 줄 닫힘(저장 안 함)", page.locator("input[data-version-name]").count() == 0 and len(division(report)["versions"]) == 1)
        api("PUT", f"/api/docs/{report}/divisions/settings", json={"values": {"stages": [3], "orgs": {"lead": "주관 A", "joint": []}}})  # 지금 구분 기준을 다른 값으로(다른 화면에서 바꾼 것처럼) — 버전은 그대로
        page.evaluate("() => divShow()")
        page.wait_for_function("() => dv.values.stages.length === 1 && !!document.querySelector('select[data-division-version]')", timeout=30000)
        options = page.evaluate(VERSION_OPTIONS)
        check("입력이 달라지면 「지금」 표시가 빠짐", len(options) == 2 and not options[1].endswith("· 지금") and division(report)["versions"][0]["active"] is False, options)
        page.locator("select[data-division-version]").select_option(vid)
        with page.expect_response(lambda r: r.url.endswith(f"/divisions/versions/{vid}/apply") and r.request.method == "POST", timeout=30000) as version_applied:
            page.locator("[data-version-apply]").click()
        check("버전 적용 API 성공", version_applied.value.status == 200, version_applied.value.status)
        page.wait_for_function("() => dv.values.stages.length === 2 && document.querySelector('#divBox .project-sharing').dataset.division === 'confirmed'", timeout=30000)
        applied = division(report)
        check("적용 — 입력 값이 그 버전 · 프로젝트에 확정 · 같은 프로젝트의 다른 TASK 도 같은 값", applied["settings"]["values"]["stages"] == [2, 1] and bool(applied["confirmed"]) and applied["confirmed"]["valid"]
              and applied["confirmed"]["scope"] == "project" and division(other_task)["settings"] == applied["settings"], applied.get("confirmed"))
        check("적용 뒤 화면 — 「구분 기준 확정」 · 알림 · 목록의 「지금」", "프로젝트 구성 확정" in page.locator("#divBox .project-sharing").inner_text()
              and "버전 「1차년도」 을 적용했습니다" in page.locator("#toast").text_content() and page.evaluate(VERSION_OPTIONS)[1].endswith("· 지금"), page.locator("#toast").text_content())
        page.locator("[data-version-delete]").click()
        check("삭제 — 인라인 확인 줄", page.locator("[data-version-delete-ok]").is_visible() and "버전 「1차년도」 을 지울까요" in page.locator("#divBox .project-versions").inner_text())
        with page.expect_response(lambda r: r.url.endswith(f"/divisions/versions/{vid}") and r.request.method == "DELETE", timeout=30000) as version_removed:
            page.locator("[data-version-delete-ok]").click()
        check("버전 삭제 API 성공", version_removed.value.status == 200, version_removed.value.status)
        page.wait_for_selector("#divBox .project-versions .project-versions-none")
        applied = division(report)
        check("삭제 — 버전만 없어지고 지금 구분 기준·확정은 그대로", applied["versions"] == [] and applied["confirmed"]["valid"] and applied["settings"]["values"]["stages"] == [2, 1], applied.get("versions"))
        shared = applied["settings"]  # 아래 「이전 라운드는 구분 기준 보관」 이 견줄 값 — 버전 적용을 거친 지금 설정

        order = page.evaluate("() => [...document.querySelectorAll('#toolTabs [role=tab]')].filter((b) => !b.hidden && b.getClientRects().length).map((b) => b.id)")  # 보이는 탭 차례(2026-11-16 — 에이전트 · 작업 내용 · <도구> | 검증 · PDF · 기록: 이 검사는 묶음을 펴 둔다 · 작업 리스트는 상단 바 아이콘)
        after_task = order[order.index("toolTabTask") + 1] if "toolTabTask" in order[:-1] else ""
        for key, expected in [("ArrowRight", after_task), ("End", order[-1]), ("Home", order[0]), ("ArrowLeft", order[-1])]:
            if key == "ArrowRight":
                page.locator("#toolTabTask").focus()
            page.keyboard.press(key)
            check(f"패널 탭 키보드 {key}", page.evaluate("id => document.activeElement.id === id && document.activeElement.getAttribute('aria-selected') === 'true'", expected))
        check("패널 탭 줄에 「작업 리스트」 없음(상단 바 아이콘으로 — 2026-11-16)", "toolTabList" not in order and page.locator("#toolTabList").count() == 0, order)
        show_list(page)
        page.wait_for_selector("#projectList .project-task-open")
        check("프로젝트 두 개에 TASK 묶음 세 개", page.locator("#projectList > .project-group").count() == 2
              and page.locator("#projectList .project-task-open").count() == 3)
        grouped = page.evaluate("() => [...document.querySelectorAll('#projectList .project-task-open')].map(e => e.dataset.projectWork)")
        check("이관 plan·report는 작업 하나로 묶임", set(grouped) == {report, other_task, outside}, grouped)
        check("현재 작업 표시", page.locator(f'[data-project-work="{report}"]').get_attribute("aria-current") == "true")
        page.locator("#projectSearch").fill("프로젝트 B")
        check("작업 리스트 검색", page.locator("#projectList .project-task-open").count() == 1
              and page.locator("#projectList .project-task-open").get_attribute("data-project-work") == outside)
        page.locator("#projectSearch").fill("")
        page.locator("#panel").screenshot(path=str(OUT / "01_projects.png"))
        select_work(page, other_task)
        check("TASK 클릭으로 그 작업 이동", page.evaluate("id => state.id === id && state.task.job === 'plan_fit'", other_task)
              and page.locator("#taskFlow").count() == 0)
        select_work(page, outside)  # 구분 기준이 없는 프로젝트(프로젝트 B) — 「구분 기준 없음」 줄 + 「새로 만들기」(② §19)
        sharing = page.evaluate(SHARING)
        check("구분 기준 없음 줄 — 표지 · 안내 · 「새로 만들기」 · 버전 추가는 꺼짐(입력 값 없음)", sharing["kind"] == "none" and "프로젝트 구성 없음" in sharing["text"] and "새로 만드세요" in sharing["text"]
              and page.locator("[data-division-new]").is_visible() and page.locator("[data-version-add]").is_disabled(), sharing)
        page.evaluate("() => { document.getElementById('taskStage0').open = false; }")
        page.locator("[data-division-new]").click()
        page.wait_for_timeout(200)
        check("「새로 만들기」 — 1단계 「구분 기준」 을 펴고 구성 입력 칸으로 포커스", page.evaluate("() => document.getElementById('taskStage0').open && document.getElementById('taskFrameForm').contains(document.activeElement)"))
        select_work(page, report)
        page.locator('[data-new-round="1"]').click()
        check("새 라운드는 처음 올린 원본이 기본 · 현재 수정본도 선택 가능", page.locator("#projectRoundSource").input_value() == "original"
              and page.locator("#projectRoundSource option").evaluate_all("items => items.map(e => e.value)") == ["original", "current"])
        page.locator("#projectNewRound").get_by_role("button", name="닫기", exact=True).click()
        branched = new_round(page, report, "current")
        new_report, new_plan = branched["docId"], branched["mapping"][plan]
        check("새 라운드는 같은 TASK의 문서만 복사", branched["round"] == 2 and branched["sourceRound"] == 1 and set(branched["mapping"]) == {plan, report}, branched)
        check("현재 수정본 복사", api("GET", f"/api/docs/{new_report}/download").content == before)
        check("이전 라운드 수정본 그대로 보존", api("GET", f"/api/docs/{report}/download").content == before)
        page.wait_for_function("id => peerShown() === id", arg=new_plan, timeout=30000)
        scope = page.evaluate(SCOPE)
        check("새 라운드 첨부·둘째 면이 새 문서로 전환", scope["slots"] == {"plan": new_plan, "report": new_report}
              and all(set(options) == {new_plan, new_report} for options in scope["options"]) and scope["shown"] == new_plan, scope)
        changed = api("PUT", f"/api/docs/{new_report}/divisions/settings", json={"values": CHANGED}).json()["settings"]
        check("새 라운드와 같은 프로젝트 최신 TASK에 구분 기준 공유", division(new_plan)["settings"] == changed and division(other_task)["settings"] == changed)
        check("이전 라운드는 구분 기준 보관", division(report)["settings"] == shared and not division(report)["projectSharing"]["shared"])
        check("공유 정보 변경이 다른 프로젝트에 영향 없음", division(outside)["settings"] is None)
        page.locator(".project-round-label select").select_option("1")
        wait_work(page, report)
        check("라운드 선택으로 이전 작업 복귀", "이전 라운드 보관" in page.locator(".project-sharing").inner_text())
        show_list(page)
        check("이전 라운드 목록에서 기존 작업 유지", page.locator(f'.project-previous [data-project-work="{report}"]').count() == 1
              and page.locator(f'.project-task-open[data-project-work="{new_report}"]').count() == 1)
        page.locator("#panel").screenshot(path=str(OUT / "02_previous_round.png"))
        page.locator("#toolTabTask").click()
        restored = new_round(page, report, "original")
        restored_report = restored["docId"]
        restored_text = [b.get("text", "") for b in paragraphs(api("GET", f"/api/docs/{restored_report}").json()["blocks"])]
        check("원본에서 새 라운드 — Round 3, Round 1 원문 복원", restored["round"] == 3 and restored["sourceRound"] == 1
              and para["text"] in restored_text and not any(marker in text for text in restored_text), restored)
        check("새 분기 뒤에도 이전 두 라운드 문서 보존", api("GET", f"/api/docs/{report}/download").content == before
              and api("GET", f"/api/docs/{new_report}/download").content == before)
        saved = {w["id"]: w["task"] for w in api("GET", "/api/works").json()}
        check("기존 작업의 프로젝트·TASK·라운드는 변경 안 됨", all(saved[wid] == task for wid, task in old_task.items()))

        # 프로젝트 고르기 목록(spec_작업 ② §19) — 프로젝트 없는 문서에서: 모든 프로젝트 + 구분 기준 표지 · 고르면 그 TASK 의 최신 라운드(Round 3)로 들어가 프로젝트의 구분 기준을 가져온다
        joiner = api("POST", "/api/samples/" + quote("기술수요조사서.hwpx") + "?new=1").json()["docId"]
        api("PUT", f"/api/works/{joiner}/task", json={"kind": "rnd", "file": "", "project": "", "job": "plan_to_report"})
        page.evaluate("id => openWork(id)", joiner)
        page.wait_for_function("id => state.id === id && !!document.querySelector('#doc .para')", arg=joiner, timeout=120000)
        page.evaluate("() => showTab('Div')")
        wait_work(page, joiner)
        page.wait_for_selector('#divBox input[data-task="project"]')
        check("프로젝트가 없으면 구분 기준 줄·버전 줄 없음", page.locator("#divBox .project-sharing").count() == 0 and page.locator("#divBox .project-versions").count() == 0)
        page.locator('#divBox input[data-task="project"]').click()
        page.wait_for_function("() => document.querySelectorAll('#taskProjectList [data-division]').length === 2", timeout=30000)
        listed = page.evaluate("() => [...document.querySelectorAll('#taskProjectList [role=option]')].map(o => [o.dataset.project, o.querySelector('[data-division]').dataset.division, o.innerText])")
        check("프로젝트 고르기 목록 — 모든 프로젝트 · 구분 기준 있음/없음 표지", [x[:2] for x in listed] == [["프로젝트 A", "has"], ["프로젝트 B", "none"]]
              and "프로젝트 구성 있음" in listed[0][2] and "프로젝트 구성 없음" in listed[1][2], listed)
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{joiner}/task") and r.request.method == "PUT", timeout=30000) as joined:
            page.locator("#taskProjectList [role=option]", has_text="프로젝트 A").click()
        check("고르면 그 프로젝트의 그 TASK 최신 라운드로 들어감(Round 3 — 화면은 round 를 안 보내고 서버가 정한다 · 전에는 늘 1) · division: adopted", joined.value.status == 200
              and joined.value.json()["task"]["project"] == "프로젝트 A" and "round" not in joined.value.request.post_data_json
              and joined.value.json()["task"].get("round") == 3 and joined.value.json().get("division") == "adopted", (joined.value.request.post_data_json, joined.value.json()))
        page.wait_for_function("""() => state.task.project === '프로젝트 A' && taskRound() === 3 && (document.querySelector('#divBox .project-sharing') || { dataset: {} }).dataset.division === 'has'
            && document.getElementById('toast').textContent.includes('가져왔습니다')""", timeout=30000)
        joined_view = division(joiner)
        check("들어간 문서 — 구분 기준 공유 · 프로젝트의 값을 가져옴 · 알림 · 「프로젝트 공유」 줄", joined_view["projectSharing"]["shared"] and joined_view["settings"] == changed
              and "프로젝트 「프로젝트 A」 의 구성을 가져왔습니다" in page.locator("#toast").text_content() and "프로젝트 공유" in page.locator("#divBox .project-sharing").inner_text(), joined_view["projectSharing"])

        # 새 파일 시작 경로도 실제 업로드·start-task API를 쓴다. 첫 분석은 별도 검사이므로 호출만 센다.
        show_list(page)
        if not page.locator("#projectCreate").evaluate("e => e.open"):
            page.locator("#projectCreate > summary").click()
        page.locator("#projectStartName").click()  # 「새 TASK 시작」 의 프로젝트 칸도 같은 고르기 목록(② §19) — 지금 프로젝트가 미리 적혀 있어도 모든 프로젝트가 보인다
        page.wait_for_selector("#projectStartList [role=option]")
        start_names = page.locator("#projectStartList [role=option]").evaluate_all("items => items.map(e => e.dataset.project)")
        check("새 TASK 시작의 프로젝트 칸 — 적힌 값과 상관없이 모든 프로젝트 · datalist 없음", page.locator("#projectStartName").input_value() == "프로젝트 A"
              and start_names == ["프로젝트 A", "프로젝트 B"] and page.locator("#projectStartNames").count() == 0, start_names)
        page.locator("#projectStartName").fill("프로젝트 C")
        check("없는 이름을 적으면 「새 프로젝트로」 줄", page.locator("#projectStartList [data-project-new]").count() == 1)
        page.locator("#projectStartTask").focus()
        check("칸을 떠나면 목록 닫힘 · 적은 이름은 그대로", page.locator("#projectStartList").count() == 0 and page.locator("#projectStartName").input_value() == "프로젝트 C")
        page.locator("#projectStartTask").select_option("plan_fit")
        page.evaluate("() => { window.__savedFirstRun = firstRun; window.__projectFirstRunCount = 0; firstRun = () => { window.__projectFirstRunCount += 1; }; }")
        with page.expect_file_chooser() as chosen:
            page.locator("#projectStartUpload").click()
        with page.expect_response(lambda r: r.url.endswith("/start-task") and r.request.method == "POST", timeout=120000) as started:
            chosen.value.set_files(str(ROOT / "samples" / "기술수요조사서.hwpx"))
        check("새 TASK 파일 올리기 — start-task API 성공", started.value.status == 200, started.value.status)
        uploaded = started.value.json()
        wait_work(page, uploaded["docId"])
        check("새 프로젝트 파일은 선택한 TASK·Round 1로 열림", uploaded["round"] == 1 and page.evaluate("() => state.task.project === '프로젝트 C' && state.task.job === 'plan_fit' && taskRound() === 1"))
        check("새 파일 첫 분석 연결은 한 번", page.evaluate("() => window.__projectFirstRunCount") == 1)
        page.evaluate("() => { firstRun = window.__savedFirstRun; delete window.__savedFirstRun; }")
        after_upload = {w["id"]: w["task"] for w in api("GET", "/api/works").json()}
        check("새 파일 시작도 기존 모든 라운드 보존", all(after_upload[wid] == task for wid, task in saved.items())
              and api("GET", f"/api/docs/{report}/download").content == before and api("GET", f"/api/docs/{new_report}/download").content == before)

        page.evaluate("() => { colSizers.find(c => c.box === 'panel').w = 320; colsApply(); }")
        show_list(page)
        page.wait_for_timeout(200)
        compact = page.evaluate("""() => { const p = document.getElementById('panel'), box = document.getElementById('projectWorkspace');
          return {width:p.getBoundingClientRect().width, overflow:box.scrollWidth-box.clientWidth,
            tabs:document.getElementById('toolTabs').scrollWidth-document.getElementById('toolTabs').clientWidth}; }""")
        check("320px 패널 — 작업 리스트·탭 가로 넘침 없음", round(compact["width"]) == 320 and compact["overflow"] <= 1 and compact["tabs"] <= 1, compact)
        page.locator("#panel").screenshot(path=str(OUT / "03_projects_320.png"))
        page.locator("#toolTabTask").click()
        page.wait_for_selector(".project-round-row")
        check("320px 패널 — 프로젝트·TASK·라운드 입력 넘침 없음", page.evaluate("() => { const e = document.querySelector('#divBox .dv-task'); return e.scrollWidth <= e.clientWidth + 1; }"))

        # 프로젝트 이름 변경 · 삭제(spec_작업 ② §17) — ⋯ → 인라인 줄, 모달 없음. 320px 폭 그대로.
        dialogs = []
        page.on("dialog", lambda dialog: dialogs.append(dialog.message))
        current = uploaded["docId"]
        tasks_a = {wid: task for wid, task in after_upload.items() if (task or {}).get("project") == "프로젝트 A"}
        overflow = "() => { const box = document.getElementById('projectWorkspace'); return box.scrollWidth - box.clientWidth; }"
        show_list(page)
        check("미지정 묶음에는 ⋯ 없음 · 이름 있는 프로젝트마다 ⋯", page.locator("[data-project-menu]").count() == 3
              and page.locator('[data-project-menu="프로젝트 B"]').get_attribute("aria-expanded") == "false")
        page.locator('[data-project-menu="프로젝트 B"]').click()
        check("⋯ — 이름 변경·삭제 줄", page.locator('[data-project-menu="프로젝트 B"]').get_attribute("aria-expanded") == "true"
              and page.locator('[data-project-rename="프로젝트 B"]').is_visible() and page.locator('[data-project-delete="프로젝트 B"]').is_visible())
        page.locator('[data-project-rename="프로젝트 B"]').click()
        name_input = page.locator('#projectList [data-project-edit="name"]')
        check("이름 줄 — 지금 이름으로 채우고 포커스", name_input.input_value() == "프로젝트 B"
              and page.evaluate("() => document.activeElement.dataset.projectEdit === 'name'"))
        name_input.fill("프로젝트 A")
        check("이미 있는 이름 — 안내 · 저장 꺼짐", page.locator("#projectList .project-edit-note").inner_text() == "같은 이름의 프로젝트가 이미 있습니다"
              and page.locator('#projectList [data-project-edit="save"]').is_disabled())
        name_input.press("Escape")
        check("Esc — 이름 줄 닫고 「이름 변경」 으로 포커스", page.locator('#projectList [data-project-edit="name"]').count() == 0
              and page.evaluate("() => document.activeElement.dataset.projectEdit === 'rename'"))
        page.locator('[data-project-rename="프로젝트 B"]').click()
        name_input.fill("  프로젝트   B2 ")
        check("320px — 이름 줄 가로 넘침 없음", page.evaluate(overflow) <= 1, page.evaluate(overflow))
        page.locator("#panel").screenshot(path=str(OUT / "04_project_rename.png"))
        with page.expect_response(lambda r: "/api/projects/" in r.url and r.request.method == "PUT", timeout=30000) as renamed:
            name_input.press("Enter")
        check("이름 변경 API 성공", renamed.value.status == 200, renamed.value.status)
        page.wait_for_selector('[data-project-menu="프로젝트 B2"]')
        tasks = {w["id"]: w["task"] for w in api("GET", "/api/works").json()}
        check("이름 변경 — 문서가 새 이름으로 · 옛 묶음 없음", tasks[outside]["project"] == "프로젝트 B2"
              and page.locator('[data-project-menu="프로젝트 B"]').count() == 0, tasks[outside])
        check("이름 변경 뒤 포커스는 새 이름의 ⋯", page.evaluate("() => document.activeElement.dataset.projectMenu === '프로젝트 B2'"))
        check("다른 프로젝트 문서는 그대로", all(tasks[wid] == task for wid, task in tasks_a.items()))

        page.locator(f'[data-project-menu="프로젝트 C"]').click()
        page.locator('[data-project-rename="프로젝트 C"]').click()
        name_input.fill("프로젝트 C2")
        page.locator('#projectList [data-project-edit="save"]').click()
        page.wait_for_function("() => state.task.project === '프로젝트 C2' && !!document.querySelector('[data-project-menu=\"프로젝트 C2\"]') && !projectStarting", timeout=30000)
        sharing = division(current)["projectSharing"]
        check("지금 문서의 프로젝트 이름 변경 — 화면 task · 공유 구분 기준이 새 이름", sharing["project"] == "프로젝트 C2" and sharing["shared"]
              and page.evaluate("id => state.id === id", current), sharing)

        api("POST", f"/api/docs/{joiner}/divisions/versions", json={"name": "보관"})  # 프로젝트 A 에 구분 기준 버전 하나 — 삭제 확인 줄이 버전도 지워짐을 알린다(② §19)
        page.locator('[data-project-menu="프로젝트 A"]').click()
        page.locator('[data-project-delete="프로젝트 A"]').click()
        try:
            page.wait_for_function("() => { const e = document.querySelector('#projectList .project-edit-text'); return !!e && e.textContent.includes('프로젝트 구성 버전 1개도 지워집니다'); }", timeout=15000)
        except Exception:
            pass
        check("버전이 있는 프로젝트의 삭제 확인 줄 — 「구분 기준 버전 N개도 지워집니다」", "프로젝트 구성 버전 1개도 지워집니다" in page.locator("#projectList .project-edit-text").inner_text()
              and page.evaluate(overflow) <= 1, page.locator("#projectList .project-edit-text").inner_text())
        page.locator('#projectList [data-project-edit="cancel"]').click()
        page.locator('[data-project-menu="프로젝트 B2"]').click()
        page.locator('[data-project-delete="프로젝트 B2"]').click()
        check("삭제 확인 줄 — 문서 수 · 단추 셋 · 포커스는 취소", "문서 1개" in page.locator("#projectList .project-edit-text").inner_text()
              and page.locator('#projectList [data-project-edit="keep"]').is_visible() and page.locator('#projectList [data-project-edit="purge"]').is_visible()
              and page.evaluate("() => document.activeElement.dataset.projectEdit === 'cancel'"))
        check("320px — 삭제 확인 줄 가로 넘침 없음", page.evaluate(overflow) <= 1, page.evaluate(overflow))
        page.locator("#panel").screenshot(path=str(OUT / "05_project_delete.png"))
        page.locator('#projectList [data-project-edit="cancel"]').click()
        kept = {w["id"]: w["task"] for w in api("GET", "/api/works").json()}
        check("취소 — 확인 줄 닫힘 · 문서 그대로", page.locator("#projectList .project-edit-text").count() == 0
              and kept[outside]["project"] == "프로젝트 B2")
        page.locator('[data-project-delete="프로젝트 B2"]').click()
        with page.expect_response(lambda r: "/api/projects/" in r.url and r.request.method == "DELETE", timeout=30000) as released:
            page.locator('#projectList [data-project-edit="keep"]').click()
        check("프로젝트만 해제 API 성공", released.value.status == 200 and released.value.url.endswith("docs=keep"), released.value.url)
        page.wait_for_function("() => !document.querySelector('[data-project-menu=\"프로젝트 B2\"]') && !projectStarting", timeout=30000)
        tasks = {w["id"]: w["task"] for w in api("GET", "/api/works").json()}
        check("프로젝트만 해제 — 문서는 남고 미지정", outside in tasks and tasks[outside]["project"] == "" and "round" not in tasks[outside], tasks.get(outside))
        check("해제한 문서는 「프로젝트 미지정」 묶음에", page.locator(f'[data-project-work="{outside}"]').count() == 1
              and page.locator("#projectList .project-group-title strong", has_text="프로젝트 미지정").count() == 1)

        # ---- 프로젝트 구성 초기화 · 문서 없는 프로젝트(spec_작업 ② §17, 2026-11-13) — 320px 폭 그대로
        # 초기화: 문서 있는 프로젝트의 ⋯ 셋째 단추 → 인라인 확인 줄 → DELETE …?docs=reset. 프로젝트 구성(값·확정·버전)만 지워지고 문서는 프로젝트에 그대로
        page.locator('[data-project-menu="프로젝트 C2"]').click()
        try:
            page.wait_for_function("() => { const b = document.querySelector('[data-project-reset=\"프로젝트 C2\"]'); return !!b && b.disabled; }", timeout=15000)
        except Exception:
            pass
        check("프로젝트 구성이 없는 프로젝트 — 「초기화」 꺼짐(지울 것이 없음 · 까닭은 도움말)", page.locator('[data-project-reset="프로젝트 C2"]').is_disabled()
              and "지울 프로젝트 구성이 없습니다" in page.locator('[data-project-reset="프로젝트 C2"]').get_attribute("title"))
        page.locator('[data-project-menu="프로젝트 C2"]').click()
        page.evaluate("id => projectOpen(id)", joiner)  # 프로젝트 A(구성 값 · 버전 「보관」)의 문서를 열어 둔 채 초기화한다
        wait_work(page, joiner)
        check("초기화 전 — 프로젝트 구성 있음 줄 · 버전 하나", page.evaluate(SHARING)["kind"] == "has" and len(page.evaluate(VERSION_OPTIONS)) == 2, page.evaluate(SHARING))
        show_list(page)
        page.locator('[data-project-menu="프로젝트 A"]').click()
        page.locator('[data-project-reset="프로젝트 A"]').click()
        try:
            page.wait_for_function("() => { const e = document.querySelector('#projectList .project-edit-text'); return !!e && e.textContent.includes('버전 1개가 지워집니다'); }", timeout=15000)
        except Exception:
            pass
        reset_text = page.locator("#projectList .project-edit-text").inner_text()
        docs_a = len(tasks_a)
        check("초기화 확인 줄 — 무엇이 지워지고 무엇이 남는지 · 단추 「초기화」·「취소」 · 포커스는 취소", "「프로젝트 A」 의 프로젝트 구성을 초기화할까요? 구성 값·확정·버전 1개가 지워집니다" in reset_text
              and f"문서 {docs_a}개는 프로젝트에 그대로 남고, 문서에 이미 반영한 내용은 바뀌지 않습니다" in reset_text and page.locator('#projectList [data-project-edit="reset-ok"]').inner_text() == "초기화"
              and page.evaluate("() => document.activeElement.dataset.projectEdit === 'cancel'") and page.locator('#projectList [data-project-edit="keep"]').count() == 0, reset_text)
        check("320px — 초기화 확인 줄 가로 넘침 없음", page.evaluate(overflow) <= 1, page.evaluate(overflow))
        page.locator("#panel").screenshot(path=str(OUT / "06_project_reset.png"))
        with page.expect_response(lambda r: "/api/projects/" in r.url and r.request.method == "DELETE", timeout=30000) as reset_done:
            page.locator('#projectList [data-project-edit="reset-ok"]').click()
        check("초기화 API 성공(?docs=reset)", reset_done.value.status == 200 and reset_done.value.url.endswith("docs=reset") and reset_done.value.json().get("docs") == "reset", reset_done.value.url)
        page.wait_for_function("() => !projectStarting && document.getElementById('toast').textContent.includes('초기화했습니다')", timeout=30000)
        tasks = {w["id"]: w["task"] for w in api("GET", "/api/works").json()}
        after_reset = division(joiner)
        check("초기화 — 구성 값·확정·버전이 지워짐 · 문서는 프로젝트에 그대로 · 이전 라운드에 보관한 값은 그대로", after_reset["settings"] is None and not after_reset["confirmed"] and after_reset["versions"] == []
              and after_reset["projectSharing"]["shared"] and all(tasks[wid] == task for wid, task in tasks_a.items()) and division(report)["settings"] == shared,
              (after_reset["settings"], after_reset["confirmed"], after_reset["versions"]))
        check("초기화 알림", "프로젝트 「프로젝트 A」 의 구성을 초기화했습니다 — 새로 만드세요" in page.locator("#toast").text_content(), page.locator("#toast").text_content())
        page.locator("#toolTabTask").click()
        wait_work(page, joiner)
        page.wait_for_function("() => (document.querySelector('#divBox .project-sharing') || { dataset: {} }).dataset.division === 'none'", timeout=30000)
        sharing = page.evaluate(SHARING)
        check("초기화 뒤 화면 — 「프로젝트 구성 없음 … 새로 만드세요」 줄 · 「버전 없음」", "프로젝트 구성 없음" in sharing["text"] and "새로 만드세요" in sharing["text"]
              and page.locator("#divBox .project-versions .project-versions-none").count() == 1 and page.locator("select[data-division-version]").count() == 0, sharing)
        # 문서 없는 프로젝트: 문서를 지워 프로젝트 구성 기록만 남긴다 → 작업 리스트(문서 있는 프로젝트 뒤) · 고르기 목록에 「문서 없음」 → ⋯ 에 초기화 없음 → 「삭제」 하나
        lonely = upload(project="프로젝트 빈", job="plan_fit")
        api("PUT", f"/api/docs/{lonely}/divisions/settings", json={"values": VALUES})
        api("POST", f"/api/docs/{lonely}/divisions/versions", json={"name": "남은 버전"})
        api("DELETE", f"/api/works/{lonely}")
        show_list(page)
        page.locator("#projectWorkspace .project-list-head button").click()  # 새로고침 — 작업 목록 + 프로젝트 정보
        page.wait_for_selector('#projectList [data-project-empty="프로젝트 빈"]', timeout=30000)
        empty_text = page.locator('#projectList [data-project-empty="프로젝트 빈"]').inner_text()
        check("문서 없는 프로젝트가 작업 리스트에 — 이름 · 「문서 없음」 · 남은 것(프로젝트 구성 · 버전 수) · 문서 있는 프로젝트 뒤", "프로젝트 빈" in empty_text and "문서 없음" in empty_text
              and "문서가 없는 프로젝트입니다 — 프로젝트 구성(버전 1개)만 남아 있습니다" in empty_text
              and page.evaluate("() => document.querySelector('#projectList > .project-group:last-of-type').dataset.projectEmpty === '프로젝트 빈'"), empty_text)
        page.locator("#projectSearch").fill("프로젝트 빈")
        check("문서 없는 프로젝트도 검색에 걸림", page.locator('#projectList [data-project-empty="프로젝트 빈"]').count() == 1 and page.locator("#projectList .project-task-open").count() == 0)
        page.locator("#projectSearch").fill("")
        page.locator("#projectStartName").click()
        page.wait_for_selector('#projectStartList [data-project="프로젝트 빈"]')
        empty_tags = page.locator('#projectStartList [data-project="프로젝트 빈"] .project-combo-tag').all_text_contents()
        check("고르기 목록에도 — 구성 표지 · 버전 수 · 「문서 없음」", empty_tags == ["프로젝트 구성 있음", "버전 1개", "문서 없음"], empty_tags)
        page.keyboard.press("Escape")
        page.locator('[data-project-menu="프로젝트 빈"]').click()
        check("문서 없는 프로젝트의 ⋯ — 이름 변경 · 삭제(초기화 없음)", page.locator('[data-project-rename="프로젝트 빈"]').is_visible() and page.locator('[data-project-delete="프로젝트 빈"]').is_visible()
              and page.locator('[data-project-reset="프로젝트 빈"]').count() == 0)
        page.locator('[data-project-delete="프로젝트 빈"]').click()
        try:
            page.wait_for_function("() => { const e = document.querySelector('#projectList .project-edit-text'); return !!e && e.textContent.includes('버전 1개'); }", timeout=15000)
        except Exception:
            pass
        check("문서 없는 프로젝트의 삭제 확인 줄 — 지워지는 것은 프로젝트 구성뿐 · 단추는 「삭제」 하나 + 「취소」", "「프로젝트 빈」 프로젝트를 지울까요? 문서는 없고 프로젝트 구성(버전 1개)만 지워집니다" in page.locator("#projectList .project-edit-text").inner_text()
              and page.locator('#projectList [data-project-edit="remove"]').inner_text() == "삭제" and page.locator('#projectList [data-project-edit="keep"]').count() == 0
              and page.locator('#projectList [data-project-edit="purge"]').count() == 0 and page.evaluate(overflow) <= 1, page.locator("#projectList .project-edit-text").inner_text())
        page.locator("#panel").screenshot(path=str(OUT / "07_project_empty.png"))
        with page.expect_response(lambda r: "/api/projects/" in r.url and r.request.method == "DELETE", timeout=30000) as emptied:
            page.locator('#projectList [data-project-edit="remove"]').click()
        check("문서 없는 프로젝트 삭제 API 성공(?docs=keep)", emptied.value.status == 200 and emptied.value.url.endswith("docs=keep"), emptied.value.url)
        page.wait_for_function("() => !document.querySelector('#projectList [data-project-empty]') && !projectStarting", timeout=30000)
        check("삭제 뒤 — 프로젝트 목록(API)과 작업 리스트에서 사라짐", all(p["name"] != "프로젝트 빈" for p in api("GET", "/api/projects").json()["projects"])
              and page.locator('[data-project-menu="프로젝트 빈"]').count() == 0)
        # TASK · 문서 지우기(spec_작업 ② §7 「작업 지우기」 · §17, 2026-11-16) — TASK 줄 끝 「지우기」 = 그 라운드의 문서 전부 · 문서 줄 끝 × = 그 문서 하나 → 줄 아래 확인 줄(창 없음). 320px 폭 그대로.
        gone = "프로젝트 지움"
        g_plan, g_report, g_extra = upload(project=gone), upload("report", project=gone), upload(project=gone)  # 이관 Round 1 — 문서 셋
        g_fit = upload(project=gone, job="plan_fit")  # 양식 맞추기 Round 1 → 아래에서 Round 2 를 만든다(이전 라운드가 남는다는 글)
        g_fit2 = api("POST", f"/api/works/{g_fit}/round", json={"source": "original"}).json()["docId"]
        page.locator("#projectWorkspace .project-list-head button").click()  # 새로고침
        page.wait_for_selector(f'[data-project-work="{g_report}"]', timeout=30000)
        g_round, g_key = f'round:["{gone}","plan_to_report",1]', lambda wid: f"file:{wid}"
        drop_btn = lambda key: page.locator("#projectList [data-project-drop]").evaluate_all("(list, key) => list.findIndex((b) => b.dataset.projectDrop === key)", key)
        drop = lambda key: page.locator("#projectList [data-project-drop]").nth(drop_btn(key))
        works_now = lambda: {w["id"] for w in api("GET", "/api/works").json()}
        opened = page.evaluate("() => state.id")  # 지금 연 문서 — 다른 문서를 지워도 그대로여야 한다
        check("TASK 줄마다 「지우기」 · 문서 줄 × 는 문서가 둘 이상인 묶음에만", drop_btn(g_round) >= 0 and drop(g_round).inner_text() == "지우기" and drop_btn(g_key(g_plan)) >= 0
              and drop_btn(g_key(g_fit2)) < 0 and page.locator("#projectList .project-task-open").count() == page.locator("#projectList .project-task-del").count())
        page.locator(f'[data-project-work="{g_report}"]').locator("xpath=ancestor::div[contains(@class, 'project-task-item')]").locator(".project-task-files > summary").click()
        drop(g_key(g_extra)).click()
        drop_text = page.locator("#projectList .project-drop .project-edit-text").inner_text()
        check("문서 줄 × — 그 줄 아래 확인 줄(문서 이름 · 되살릴 수 없음) · 포커스는 취소 · 아직 안 지움", "문서 「기술수요조사서.hwpx」을(를) 지울까요?" in drop_text and "되살릴 수 없습니다" in drop_text
              and page.evaluate("() => document.activeElement.dataset.projectEdit === 'drop-cancel'") and drop(g_key(g_extra)).get_attribute("aria-expanded") == "true" and g_extra in works_now(), drop_text)
        check("320px — 지우기 확인 줄 가로 넘침 없음", page.evaluate(overflow) <= 1, page.evaluate(overflow))
        page.locator("#panel").screenshot(path=str(OUT / "08_task_drop_file.png"))
        page.keyboard.press("Escape")
        check("Esc — 확인 줄 닫힘 · 포커스는 그 × 로 · 문서 그대로", page.locator("#projectList .project-drop").count() == 0
              and page.evaluate("key => document.activeElement.dataset.projectDrop === key", g_key(g_extra)) and g_extra in works_now())
        drop(g_key(g_extra)).click()
        page.locator('[data-project-menu="프로젝트 A"]').click()
        check("확인 줄은 한 번에 하나 — 프로젝트 ⋯ 를 열면 지우기 확인 줄이 닫힘", page.locator("#projectList .project-drop").count() == 0 and page.locator("#projectList .project-edit").count() == 1)
        drop(g_key(g_extra)).click()
        check("… 지우기 확인 줄을 열면 프로젝트 ⋯ 줄이 닫힘", page.locator("#projectList .project-drop").count() == 1 and page.locator("#projectList .project-edit").count() == 1
              and page.locator('[data-project-menu="프로젝트 A"]').get_attribute("aria-expanded") == "false")
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{g_extra}") and r.request.method == "DELETE", timeout=30000) as dropped:
            page.locator('#projectList [data-project-edit="drop-ok"]').click()
        page.wait_for_function("id => !document.querySelector(`[data-project-file=\"${id}\"]`) && !projectStarting && !projectDrop", arg=g_extra, timeout=30000)
        check("문서 하나 지우기 — DELETE /api/works/{id} · 그 문서만 없어지고 같은 묶음의 다른 문서는 그대로 · 알림", dropped.value.status == 200 and g_extra not in works_now() and {g_plan, g_report} <= works_now()
              and "문서 「기술수요조사서.hwpx」을(를) 지웠습니다" in page.locator("#toast").text_content() and bool(opened) and page.evaluate("id => state.id === id", opened), (page.locator("#toast").text_content(), opened, page.evaluate("() => state.id")))
        drop(g_round).click()
        drop_text = page.locator("#projectList .project-drop").inner_text()
        check("TASK 줄 「지우기」 — 「프로젝트 · TASK · Round 의 문서 N개」 + 문서 이름 목록", f"프로젝트 「{gone}」 · TASK 「사업계획서 → 연차보고서 이관」 · Round 1 의 문서 2개를 지울까요?" in drop_text
              and page.locator("#projectList .project-drop .work-drop-names > li").count() == 2 and "시작 화면으로" not in drop_text and "이전 라운드" not in drop_text, drop_text)
        check("320px — 라운드 지우기 확인 줄 가로 넘침 없음", page.evaluate(overflow) <= 1, page.evaluate(overflow))
        page.locator("#panel").screenshot(path=str(OUT / "09_task_drop_round.png"))
        deleted = []
        page.on("response", lambda r: deleted.append(r.url.rsplit("/", 1)[1]) if r.request.method == "DELETE" and "/api/works/" in r.url and r.status == 200 else None)
        page.locator('#projectList [data-project-edit="drop-ok"]').click()
        page.wait_for_function("id => !document.querySelector(`[data-project-work=\"${id}\"]`) && !projectStarting && !projectDrop", arg=g_report, timeout=30000)
        check("라운드 지우기 — 그 라운드의 문서를 다 지움 · 같은 프로젝트의 다른 TASK 는 그대로 · 알림", set(deleted) == {g_plan, g_report} and not ({g_plan, g_report} & works_now()) and {g_fit, g_fit2} <= works_now()
              and "의 문서 2개를 지웠습니다" in page.locator("#toast").text_content(), (deleted, page.locator("#toast").text_content()))
        drop(f'round:["{gone}","plan_fit",2]').click()
        drop_text = page.locator("#projectList .project-drop .project-edit-text").inner_text()
        check("최신 라운드를 지울 때 — 「이전 라운드 1개는 남습니다」", "이전 라운드 1개는 남습니다" in drop_text, drop_text)
        page.locator('#projectList [data-project-edit="drop-ok"]').click()
        page.wait_for_function("id => !document.querySelector(`[data-project-work=\"${id}\"]`) && !projectStarting && !projectDrop", arg=g_fit2, timeout=30000)
        check("최신 라운드를 지우면 이전 라운드가 진행 작업으로", g_fit2 not in works_now() and g_fit in works_now()
              and page.locator(f'.project-previous [data-project-work="{g_fit}"]').count() == 0 and "진행 작업" in page.locator(f'[data-project-work="{g_fit}"]').inner_text())
        page.evaluate("id => projectOpen(id)", g_fit)  # 지금 연 문서를 지우면 — 글에 알리고, 지운 뒤 시작 화면으로
        wait_work(page, g_fit)
        show_list(page)
        drop(f'round:["{gone}","plan_fit",1]').click()
        drop_text = page.locator("#projectList .project-drop .project-edit-text").inner_text()
        check("지금 연 문서를 지울 때 — 「지금 연 문서가 들어 있어 시작 화면으로 돌아갑니다」", "지금 연 문서가 들어 있어 시작 화면으로 돌아갑니다" in drop_text, drop_text)
        page.locator('#projectList [data-project-edit="drop-ok"]').click()
        page.wait_for_function("() => !state.id && !document.getElementById('empty').hidden", timeout=30000)
        check("지금 연 문서 지우기 — 문서가 없어지고 화면은 시작 화면으로", g_fit not in works_now() and requests.get(f"{BASE}/api/docs/{g_fit}", timeout=30).status_code == 404)
        page.evaluate("id => projectOpen(id)", current)  # 아래 「문서까지 삭제」 는 지금 연 문서(프로젝트 C2)로 본다
        wait_work(page, current)
        show_list(page)
        page.locator('[data-project-menu="프로젝트 C2"]').click()
        page.locator('[data-project-delete="프로젝트 C2"]').click()
        with page.expect_response(lambda r: "/api/projects/" in r.url and r.request.method == "DELETE", timeout=30000) as purged:
            page.locator('#projectList [data-project-edit="purge"]').click()
        check("문서까지 삭제 API 성공", purged.value.status == 200 and purged.value.url.endswith("docs=delete"), purged.value.url)
        page.wait_for_function("() => !state.id && !document.getElementById('empty').hidden", timeout=30000)
        tasks = {w["id"]: w["task"] for w in api("GET", "/api/works").json()}
        check("문서까지 삭제 — 지금 문서가 지워지고 화면은 닫힘", current not in tasks and requests.get(f"{BASE}/api/docs/{current}", timeout=30).status_code == 404)
        check("삭제 뒤에도 다른 프로젝트·해제한 문서 그대로", all(tasks.get(wid) == task for wid, task in tasks_a.items()) and outside in tasks)
        check("이름 변경·삭제에 브라우저 창(confirm·prompt) 없음", not dialogs, dialogs)
        check("화면 오류 0", not errors, errors)
        check("LLM·첫 분석 호출 없음", not llm_calls, llm_calls)
        browser.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
    log.close()

print("\n" + (f"실패 {len(fails)}개: " + ", ".join(fails) if fails else "모두 통과"))
sys.exit(1 if fails else 0)
