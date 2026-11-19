"""대시보드의 워크플로우 목록·불러오기·전환·목록에서 빼기 화면 검사.

작은 실제 HWPX + 격리 서버(PDF·LLM 끔)를 사용한다. 단계 완료는 화면 모델만
흉내 내고, 목록 저장·전환·다시 열기는 실제 API로 확인한다. 사용자 작업은 안 건드린다.

    python -X utf8 tools/smoke_dash_workflows_ui.py <출력 폴더> [--port 18472]
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import requests
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("out")
parser.add_argument("--port", type=int, default=18472)
args = parser.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
TMP = Path(tempfile.mkdtemp(prefix="srv-", dir=OUT))
BASE = f"http://127.0.0.1:{args.port}"
env = {**os.environ, "PYTHONUTF8": "1", "NFM_PDF": "off", "NFM_LLM_BACKEND": "off",
       **{key: str(TMP / name) for key, name in {
           "NFM_WORKS": "works", "NFM_RENDER": "render", "NFM_HEADINGS": "headings",
           "NFM_FORMS": "forms", "NFM_DIVISION_PRESETS": "presets.json",
           "NFM_STYLES": "styles", "NFM_AGENTS": "agents.json"}.items()}}
for key in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL"):
    env.pop(key, None)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen(
    [sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
    cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
errors, fails = [], []
TOGGLE = "#paneDash .dash-workflow-toggle"
LIST = "#dashWorkflowList"
LIBRARY = "#paneDash .dash-workflow-library"


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:800] if detail and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def api(method, path, **kwargs):
    response = requests.request(method, BASE + path, timeout=120, **kwargs)
    response.raise_for_status()
    return response.json()


def wait_server():
    end = time.monotonic() + 90
    while time.monotonic() < end:
        try:
            if requests.get(BASE + "/api/headings/llm", timeout=2).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.3)
    raise RuntimeError("격리 서버가 시작되지 않았습니다")


def open_list(page):
    if page.get_attribute(TOGGLE, "aria-expanded") != "true":
        page.locator(TOGGLE).click()
    page.wait_for_selector(LIST)


def open_library(page):
    open_list(page)
    if not page.locator(LIBRARY).is_visible():
        page.locator("#paneDash .dash-workflow-load").click()
    page.wait_for_selector(LIBRARY)


def workflow_button(page, job):
    row = page.locator(f'{LIST} .dash-workflow-row[data-job="{job}"]')
    return row if row.evaluate("e => e.tagName === 'BUTTON'") else row.locator("button").first


def select_workflow(page, wid, job):
    open_list(page)
    workflow_button(page, job).click()
    # state.task.job 은 전환 응답 바로 뒤에 바뀌고 대시보드 · 목록은 그 뒤에 다시 그려진다 — 그것만 기다리면 옛 목록(옛 「선택됨」)을 읽는다(같이 돌 때만 떨어지던 경합).
    # 전환이 끝나고(DWF.busy 풀림) 대시보드가 새 워크플로우로 다시 그려진 것(머리의 「워크플로우 ↗」 링크가 그 워크플로우)을 기다린 뒤, 목록도 새 「선택됨」 으로 다시 그려진 것을 본다
    page.wait_for_function("""([id, job]) => state.id === id && state.task.job === job && !DWF.busy
      && document.querySelector('#paneDash .dash-wf')?.getAttribute('href') === '/workflow#' + encodeURIComponent(job)
      && !!document.querySelector('#paneDash .dash-node')""", arg=[wid, job], timeout=60000)
    open_list(page)
    page.wait_for_selector(f'{LIST} .dash-workflow-row[data-job="{job}"][aria-current="true"]', timeout=30000)


def rows(page):
    return page.locator(f"{LIST} .dash-workflow-row").evaluate_all("""els => els.map(e => ({
      job: e.dataset.job, status: e.dataset.status, text: e.textContent,
      current: e.getAttribute('aria-current') || e.querySelector('button')?.getAttribute('aria-current') || '',
      disabled: e.tagName === 'BUTTON' ? e.disabled : !!e.querySelector('button')?.disabled
    }))""")


COMPLETE_FIT = """() => {
  window.__workflowModel = dashModel;
  dashModel = async (...args) => {
    const M = await window.__workflowModel(...args);
    if (M.job === 'plan_fit') for (const g of M.groups) for (const n of g.nodes) {
      if (dashCounted(n)) n.state = 'done';
    }
    return M;
  };
  return dashDraw(true);
}"""


def main():
    wait_server()
    sample = ROOT / "samples" / "기술수요조사서.hwpx"
    with sample.open("rb") as stream:
        wid = api("POST", "/api/docs?new=1", files={"file": (sample.name, stream)})["docId"]
    api("PUT", f"/api/works/{wid}/task", json={"kind": "rnd", "job": "plan_fit", "file": "plan", "project": "워크플로우 화면 검사", "round": 1})
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        page.add_init_script("localStorage.setItem('nfm.agentDock', 'panel');")
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text)
                if message.type == "error" and "Failed to load resource" not in message.text else None)
        page.goto(f"{BASE}/#w={wid}")
        page.wait_for_selector("#doc .para", timeout=120000)
        page.click("#tabDash")
        page.wait_for_selector("#paneDash .dash-node", timeout=60000)
        page.wait_for_selector(TOGGLE)
        open_list(page)
        initial = rows(page)
        check("현재 워크플로우가 목록에 자동으로 들어가고 선택 표시", len(initial) == 1 and initial[0]["job"] == "plan_fit" and initial[0]["current"] == "true", initial)

        # 단계 실행 결과만 완료로 흉내 낸다. 저장·목록·전환은 제품 코드를 그대로 탄다.
        page.evaluate(COMPLETE_FIT)
        page.wait_for_function("() => document.querySelector('#dashWorkflowList .dash-workflow-row[data-job=plan_fit]')?.dataset.status === 'done'", timeout=30000)
        complete = rows(page)
        check("완료 워크플로우에 완료 상태와 단계 수 표시", complete[0]["status"] == "done" and "9/9" in complete[0]["text"], complete)

        open_library(page)
        available = page.locator(f"{LIBRARY} .dash-workflow-add").evaluate_all("els => els.map(e => e.dataset.job)")
        check("불러오기 목록은 사용 가능한 워크플로우만 제공", "doc_edit" in available and "style_copy" in available and "report_merge" not in available, available)
        page.locator(f'{LIBRARY} .dash-workflow-add[data-job="doc_edit"]').click()
        page.wait_for_selector(f'{LIST} .dash-workflow-row[data-job="doc_edit"]')
        after_add = rows(page)
        check("목록에 추가해도 현재 문서와 워크플로우 유지", page.evaluate("[state.id, state.task.job]") == [wid, "plan_fit"] and len(after_add) == 2, after_add)
        extra = page.locator(f'{LIBRARY} .dash-workflow-add[data-job="doc_edit"]')
        check("이미 불러온 워크플로우 중복 추가 방지", not extra.count() or extra.is_disabled(), after_add)
        page.locator("#paneDash").screenshot(path=str(OUT / "01_workflow_list.png"))

        select_workflow(page, wid, "doc_edit")
        open_list(page)
        switched = rows(page)
        old = next(row for row in switched if row["job"] == "plan_fit")
        current = next(row for row in switched if row["job"] == "doc_edit")
        check("다른 워크플로우 선택: 같은 문서·이전 완료 기록 유지", old["status"] == "done" and "9/9" in old["text"] and current["current"] == "true", switched)
        check("반복 작업인 일반 편집은 문서 열기만으로 완료 처리하지 않음", current["status"] != "done", current)
        saved = api("GET", f"/api/works/{wid}/workflows")
        check("추가한 목록과 현재 선택을 서버에 저장", saved.get("active") == "doc_edit" and {item["job"] for item in saved.get("items", [])} == {"plan_fit", "doc_edit"}, saved)

        select_workflow(page, wid, "plan_fit")
        check("이전 워크플로우를 다시 선택하면 단계 화면으로 돌아감", "9/9" in page.locator("#paneDash .dash-count").inner_text())
        select_workflow(page, wid, "doc_edit")
        page.reload()
        page.wait_for_selector("#doc .para", timeout=120000)
        page.click("#tabDash")
        page.wait_for_selector(TOGGLE, timeout=30000)
        open_list(page)
        page.wait_for_selector(f'{LIST} .dash-workflow-row[data-job="plan_fit"][data-status="done"]', timeout=30000)
        restored = rows(page)
        check("새로고침 뒤 추가 목록·선택·이전 완료 상태 복원", page.evaluate("[state.id, state.task.job]") == [wid, "doc_edit"] and len(restored) == 2
              and any(row["job"] == "plan_fit" and "9/9" in row["text"] for row in restored), restored)

        # 1초 지켜보기에서 목록과 키보드 초점이 사라지지 않아야 한다.
        target = workflow_button(page, "plan_fit")
        target.focus()
        page.wait_for_timeout(1300)
        focus = page.evaluate("() => document.activeElement?.closest('.dash-workflow-row')?.dataset.job")
        check("주기적 갱신 중 펼친 목록과 키보드 초점 유지", page.get_attribute(TOGGLE, "aria-expanded") == "true" and focus == "plan_fit", focus)
        page.keyboard.press("Escape")
        check("Escape로 목록을 닫고 제목에 초점 복귀", page.get_attribute(TOGGLE, "aria-expanded") == "false" and page.locator(TOGGLE).evaluate("e => e === document.activeElement"))
        page.keyboard.press("Enter")
        check("Enter로 워크플로우 목록 열기", page.get_attribute(TOGGLE, "aria-expanded") == "true")

        page.evaluate("() => { DASH.busy = {label: '검사 진행 중', t0: Date.now()}; return dashDraw(true); }")
        busy = rows(page)
        check("진행 중에는 다른 워크플로우 선택 비활성", next(row for row in busy if row["job"] == "plan_fit")["disabled"], busy)
        workflow_button(page, "plan_fit").evaluate("e => e.click()")
        check("진행 중 선택으로 작업 분류가 바뀌지 않음", page.evaluate("state.task.job") == "doc_edit")
        page.evaluate("() => { DASH.busy = null; return dashDraw(true); }")

        flags = page.evaluate("""async () => {
          const checks = [];
          for (const [name, owner, key] of [['AGENT.busy', AGENT, 'busy'], ['AGENT.applying', AGENT, 'applying'], ['dv.busy', dv, 'busy']]) {
            const previous = owner[key];
            try {
              owner[key] = true; await dashDraw(true);
              const row = document.querySelector('#dashWorkflowList .dash-workflow-row[data-job=plan_fit]');
              checks.push({name, disabled: !!row?.disabled, job: state.task.job});
            } finally { owner[key] = previous; }
          }
          await dashDraw(true);
          return checks;
        }""")
        check("에이전트 실행·반영 및 구성 처리 중 전환 비활성", len(flags) == 3 and all(row["disabled"] and row["job"] == "doc_edit" for row in flags), flags)

        # 서버 실패 때 현재 선택을 먼저 바꿔 버리지 않는다.
        activate = re.compile(r"/api/works/[^/]+/workflows/activate$")
        page.route(activate, lambda route: route.fulfill(status=503, json={"detail": "검사: 전환 저장 실패"}))
        with page.expect_response(lambda response: bool(activate.search(response.url)) and response.status == 503):
            workflow_button(page, "plan_fit").click()
        page.wait_for_timeout(350)
        check("전환 API 실패 시 이전 선택·문서 유지", page.evaluate("[state.id, state.task.job]") == [wid, "doc_edit"])
        page.unroute(activate)

        with page.expect_response(lambda response: bool(activate.search(response.url)) and response.status == 200, timeout=60000):
            page.locator('[data-dash-focus="workflow:retry"]').click()
        page.wait_for_function("() => state.task.job === 'plan_fit' && !DWF.busy", timeout=60000)
        check("다시 시도는 실패한 워크플로우 선택을 실제로 재실행", page.evaluate("[state.id, state.task.job, DWF.error]") == [wid, "plan_fit", ""])

        # 응답을 붙들어 전환 중 화면을 검사한다. 실제 POST는 나중에 그대로 보낸다.
        held = []
        page.route(activate, lambda route: held.append(route))
        open_list(page)
        with page.expect_request(lambda request: bool(activate.search(request.url)) and request.method == "POST", timeout=60000):
            workflow_button(page, "doc_edit").click()
        page.wait_for_function("() => DWF.busy && state.task.job === 'plan_fit'", timeout=30000)
        blocked = page.evaluate("""async () => {
          window.__workflowExecutedDuringSwitch = false;
          await dashExec('전환 중 실행 검사', async () => { window.__workflowExecutedDuringSwitch = true; return {ok: true}; });
          const controls = [...document.querySelectorAll('#paneDash .dash-groups button, #paneDash .dash-top button')];
          return {busy: DWF.busy, job: state.task.job, controls: controls.length,
            allDisabled: controls.every(button => button.disabled), executed: window.__workflowExecutedDuringSwitch};
        }""")
        check("전환 응답 대기 중 기존 단계·묶음 단추와 실행 경로 차단", blocked["busy"] and blocked["job"] == "plan_fit" and blocked["controls"] > 0
              and blocked["allDisabled"] and not blocked["executed"], blocked)
        check("전환 요청은 하나만 보냄", len(held) == 1, len(held))
        with page.expect_response(lambda response: bool(activate.search(response.url)) and response.status == 200, timeout=60000):
            held[0].continue_()
        page.unroute(activate)
        page.wait_for_function("() => state.task.job === 'doc_edit' && !DWF.busy", timeout=60000)
        check("대기한 전환 완료 뒤 새 워크플로우 표시", page.evaluate("[state.id, state.task.job]") == [wid, "doc_edit"])

        # 좁은 실제 패널 폭에서 목록·불러오기 카드가 넘치지 않는다.
        page.set_viewport_size({"width": 1100, "height": 900})
        page.evaluate("() => document.documentElement.style.setProperty('--panel', '320px')")
        open_library(page)
        page.wait_for_timeout(350)
        measure = page.evaluate("""() => {
          const pane = document.getElementById('paneDash'), panel = document.getElementById('panel'), r = pane.getBoundingClientRect();
          return {width: Math.round(panel.getBoundingClientRect().width), overflow: pane.scrollWidth > pane.clientWidth + 1,
            drops: pane.querySelectorAll('.dash-workflow-drop').length,
            inside: [...pane.querySelectorAll('.dash-workflow-row, .dash-workflow-drop, .dash-workflow-add, .dash-workflow-toggle')]
              .every(e => {const b = e.getBoundingClientRect(); return b.right <= r.right + 1 && b.left >= r.left - 1;})};
        }""")
        check("320px 패널에서 목록(줄 옆 「목록에서 빼기」 포함)·불러오기 가로 넘침 없음", measure["width"] == 320 and not measure["overflow"] and measure["inside"] and measure["drops"] >= 1, measure)
        page.locator("#paneDash").screenshot(path=str(OUT / "02_narrow_320.png"))

        # 파일 형식 필터만 docx 상태로 흉내 낸다(문서 파일에는 쓰지 않는다).
        page.evaluate("() => { window.__formatBefore = state.format; state.format = 'docx'; return dashDraw(true); }")
        compatible = page.locator(f"{LIBRARY} .dash-workflow-add:not(:disabled)").evaluate_all("els => els.map(e => e.dataset.job)")
        check("docx에는 지원하는 추가 워크플로우만 표시", compatible == ["style_copy"], compatible)
        page.evaluate("() => { state.format = window.__formatBefore; return dashDraw(true); }")

        # 기관 문서 진행은 묶음의 공통 단계 완료와 별도로 센다.
        gather = page.evaluate("""() => {
          const model = (parts) => ({job: 'plan_merge', reg: {}, R: null, groups: [{
            nodes: [{key: 'open', state: 'done'}, {key: 'frame', state: 'done'}], parts: {rows: parts}}]});
          return {pending: dwfSnapshot(model([{state: 'done'}, {state: 'todo'}])),
            empty: dwfSnapshot(model([])), done: dwfSnapshot(model([{state: 'done'}, {state: 'done'}]))};
        }""")
        check("취합은 기관 문서가 남았거나 없으면 완료가 아님", gather["pending"]["status"] == "progress" and (gather["pending"]["done"], gather["pending"]["total"]) == (3, 4)
              and gather["empty"]["status"] != "done" and gather["done"]["status"] == "done" and (gather["done"]["done"], gather["done"]["total"]) == (4, 4), gather)

        # 준비 실패/미완료 때 임시로 그린 초기 상태로 이전 완료 기록을 덮지 않는다.
        # 앞의 재시도에서 실시간 상태가 갱신되므로 완료 기록을 API로 다시 마련한다.
        api("PUT", f"/api/works/{wid}/workflows", json={"job": "plan_fit", "status": "done", "done": 9, "total": 9})
        prime_guard = page.evaluate("""async () => {
          if (DWF.pending) await DWF.pending;
          await dwfLoad(true);
          const task = state.task, primed = DASH.primed, model = DWF.model;
          try {
            state.task = {...task, job: 'plan_fit'}; DASH.primed = '';
            await dwfObserve({job: 'plan_fit', reg: {}, R: null, groups: [{nodes: [
              {key: 'open', state: 'done'}, {key: 'values', state: 'todo'}]}]});
            return DWF.items.find(row => row.job === 'plan_fit');
          } finally { state.task = task; DASH.primed = primed; DWF.model = model; }
        }""")
        saved_fit = next(item for item in api("GET", f"/api/works/{wid}/workflows")["items"] if item["job"] == "plan_fit")
        check("준비가 끝나지 않은 모델은 기존 완료 기록을 덮지 않음", prime_guard["status"] == "done" and saved_fit["status"] == "done"
              and (saved_fit["done"], saved_fit["total"]) == (9, 9), [prime_guard, saved_fit])

        api("PUT", f"/api/works/{wid}/workflows", json={"job": "style_copy", "status": "done", "done": 4, "total": 4})
        style_guard = page.evaluate("""async () => {
          if (DWF.pending) await DWF.pending;
          await dwfLoad(true);
          const task = state.task, primed = DASH.primed, model = DWF.model, source = STYLE.save;
          try {
            state.task = {...task, job: 'style_copy'}; DASH.primed = `${dashKey()}|style_copy`; STYLE.save = null;
            const partial = {job: 'style_copy', reg: {}, R: null, groups: [{nodes: [
              {key: 'open', state: 'done'}, {key: 'find', state: 'todo'}]}]};
            const snapshot = dwfSnapshot(partial);
            await dwfObserve(partial);
            return {snapshot, row: DWF.items.find(row => row.job === 'style_copy')};
          } finally { state.task = task; DASH.primed = primed; DWF.model = model; STYLE.save = source; }
        }""")
        saved_style = next(item for item in api("GET", f"/api/works/{wid}/workflows")["items"] if item["job"] == "style_copy")
        check("아직 열지 않은 서식 복사의 임시 상태로 저장된 완료 기록을 덮지 않음", style_guard["snapshot"] is None and style_guard["row"]["status"] == "done"
              and saved_style["status"] == "done" and (saved_style["done"], saved_style["total"]) == (4, 4), [style_guard, saved_style])

        # 「목록에서 빼기」(spec_워크플로우 ② §15 — DELETE /api/works/{wid}/workflows/{job}): 지금 워크플로우가 아닌 줄에만 · 누르면 그 줄만 빠짐 · 문서 · 지금 워크플로우 · 다른 줄은 그대로.
        # 이름 끝에 받침이 있는 줄(「사업계획서 → 연차보고서 이관」 — 조사 「을」)도 하나 넣어 풍선 도움말 · 알림의 조사를 본다(「… 표준화」 · 「… 복사」 는 「를」)
        api("PUT", f"/api/works/{wid}/workflows", json={"job": "plan_to_report"})
        page.set_viewport_size({"width": 1600, "height": 1000})
        page.evaluate("() => { DWF.library = false; return dwfLoad(true).then(() => dashDraw(true)); }")
        open_list(page)
        page.wait_for_selector(f'{LIST} .dash-workflow-row[data-job="plan_to_report"]', timeout=30000)
        doc_before = api("GET", f"/api/docs/{wid}")
        lis = page.evaluate("""() => [...document.querySelectorAll('#dashWorkflowList .dash-workflow-list > li')].map((li) => {
          const row = li.querySelector('.dash-workflow-row'), drop = li.querySelector('.dash-workflow-drop');
          return {job: row && row.dataset.job, current: row && row.getAttribute('aria-current'), inRow: !!li.querySelector('.dash-workflow-row .dash-workflow-drop'),
            drop: drop && {job: drop.dataset.job, text: drop.textContent, label: drop.getAttribute('aria-label'), title: drop.title}};
        })""")
        check("「목록에서 빼기」 — 지금 워크플로우가 아닌 줄에만(그 줄의 워크플로우 · 줄 단추 밖) · 지금 워크플로우 줄에는 없음",
              sorted(x["job"] for x in lis) == ["doc_edit", "plan_fit", "plan_to_report", "style_copy"] and all((x["drop"] is None) == (x["current"] == "true") for x in lis)
              and all(x["drop"]["job"] == x["job"] and x["drop"]["text"] == "목록에서 빼기" and not x["inRow"] for x in lis if x["drop"]), lis)
        names = {"plan_fit": ("사업계획서 양식 표준화", "를"), "plan_to_report": ("사업계획서 → 연차보고서 이관", "을"), "style_copy": ("문서 서식 복사", "를")}
        want_titles = {job: f"「{name}」 {josa} 이 문서의 워크플로우 목록에서 뺍니다(다시 「＋ 워크플로우 불러오기」 로 넣을 수 있음) — 문서와 분석은 그대로이고, "
                       "그 줄의 진행 요약과 그 워크플로우로 돌아올 때 쓰던 기억(문서 역할 · 라운드)이 없어집니다" for job, (name, josa) in names.items()}
        got_titles = {x["job"]: x["drop"]["title"] for x in lis if x["drop"]}
        check("풍선 도움말 — 빼면 없어지는 것(그 줄의 진행 요약 · 그 워크플로우로 돌아올 때 쓰던 기억(문서 역할 · 라운드)) · 이름 뒤 조사는 받침대로(「… 이관」 을 · 「… 표준화」 를)",
              got_titles == want_titles, got_titles)
        drop_url = re.compile(r"/api/works/[^/]+/workflows/plan_to_report$")   # 받침이 있는 이름부터 — 알림의 조사 「을」
        with page.expect_response(lambda response: bool(drop_url.search(response.url)) and response.request.method == "DELETE", timeout=60000) as dropped:
            page.locator(f'{LIST} .dash-workflow-drop[data-job="plan_to_report"]').click()
        page.wait_for_function("() => !DWF.busy && !document.querySelector('#dashWorkflowList .dash-workflow-row[data-job=plan_to_report]')", timeout=30000)
        toast_text = page.locator("#toast").text_content() or ""
        check("알림의 조사도 받침대로(「… 이관」을 이 문서의 워크플로우 목록에서 뺐습니다)",
              dropped.value.status == 200 and toast_text == "「사업계획서 → 연차보고서 이관」을 이 문서의 워크플로우 목록에서 뺐습니다", [dropped.value.status, toast_text])
        drop_url = re.compile(r"/api/works/[^/]+/workflows/plan_fit$")
        with page.expect_response(lambda response: bool(drop_url.search(response.url)) and response.request.method == "DELETE", timeout=60000) as dropped:
            page.locator(f'{LIST} .dash-workflow-drop[data-job="plan_fit"]').click()
        page.wait_for_function("() => !DWF.busy && !document.querySelector('#dashWorkflowList .dash-workflow-row[data-job=plan_fit]')", timeout=30000)
        after = rows(page)
        saved_after, doc_after = api("GET", f"/api/works/{wid}/workflows"), api("GET", f"/api/docs/{wid}")
        toast_text = page.locator("#toast").text_content() or ""
        check("누르면 그 줄만 빠짐(DELETE 200 · 화면 목록 · 서버 목록) — 문서(차례 · 블록) · 지금 워크플로우 · 다른 줄의 완료 기록은 그대로 · 알림(「… 표준화」를)",
              dropped.value.status == 200 and sorted(row["job"] for row in after) == ["doc_edit", "style_copy"]
              and sorted(item["job"] for item in saved_after["items"]) == ["doc_edit", "style_copy"] and saved_after["active"] == "doc_edit"
              and page.evaluate("[state.id, state.task.job]") == [wid, "doc_edit"] and next(row for row in after if row["job"] == "style_copy")["status"] == "done"
              and doc_after["work"]["rev"] == doc_before["work"]["rev"] and doc_after["blocks"] == doc_before["blocks"]
              and toast_text == "「사업계획서 양식 표준화」를 이 문서의 워크플로우 목록에서 뺐습니다",
              [dropped.value.status, after, saved_after, doc_before["work"]["rev"], doc_after["work"]["rev"], toast_text])
        open_library(page)
        again = page.locator(f'{LIBRARY} .dash-workflow-add[data-job="plan_fit"]')
        check("뺀 워크플로우는 「＋ 워크플로우 불러오기」 에서 다시 넣을 수 있음", again.count() == 1 and again.is_enabled() and again.inner_text() == "목록에 추가", again.count())
        page.locator("#paneDash").screenshot(path=str(OUT / "03_drop_row.png"))
        check("콘솔 오류 없음", not errors, errors[:5])
        browser.close()


try:
    main()
finally:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(10)
    log.close()
print(f"\n{'OK' if not fails else 'FAIL'} — 실패 {len(fails)}" + (f": {fails}" if fails else ""))
sys.exit(1 if fails else 0)
