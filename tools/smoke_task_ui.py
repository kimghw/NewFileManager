"""작업 종류·첨부 파일·할 일·다른 문서(spec_작업 ② §10) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_task_ui.py <그림·임시 폴더> [--port 18162]

작은 문서 둘(기술수요조사서 hwpx·docx — 국가R&D 양식 아님)을 API 로 올려 본다: 처음엔 「작업 종류 선택」·탭 「연구개발과제」 없음 → 연구개발과제를 고르면
첨부 파일·할 일·탭이 보이고 작업에 저장 → 새로 고쳐도 그대로 → 선택을 풀면 탭이 사라지고 「검증」 으로 → 「다른 문서」 로 문서 바꾸기."""
import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--port", type=int, default=18162)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
# NFM_FLOW_EXEC=client — 이 검사는 끝점을 브라우저에서 흉내 내어(분석 · LLM 검증·보완 · 자리 연결 …) **화면의 실행 길**을 본다(묶음 연쇄 · 서버가 아직 맡지 않은 묶음이 그 길로 돈다).
# 서버 쪽 실행기(1단계 「문서 검토」 — spec_워크플로우 ② §18-10)는 흉내 낸 끝점을 모르므로 끈다 — 서버가 도는 길은 smoke_task_run_ui.py · smoke_home_dash_ui.py(진짜 끝점)와 tests/test_workflow_exec.py 가 본다
env = {**os.environ, "NFM_FLOW_EXEC": "client", "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"),
       "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:300] if detail != "" else ""), flush=True)
    if not ok:
        fails.append(name)


def upload(name):
    p = ROOT / "samples" / name
    return requests.post(f"{base}/api/docs?new=1", files={"file": (name, p.read_bytes())}, timeout=120).json()["docId"]


def open_work(page, wid):
    page.evaluate("(id) => { location.hash = '#w=' + id; }", wid)
    page.reload()
    page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=wid, timeout=120000)


VIS = "(id) => { const e = document.getElementById(id); return !e.hidden && e.getClientRects().length > 0; }"
SLOTS = "() => Object.fromEntries([...document.querySelectorAll('#taskFlow select[data-task-file]')].map((s) => [s.dataset.taskFile, s.value]))"  # 이관의 첨부 파일 칸(② §11) → {plan, report: 작업 id | ''}
STEPS = """() => [...document.querySelectorAll('#taskSteps li:not([data-step=config]):not([data-step=heads]):not([data-step=reheads]):not([data-step=headsLlm]):not([data-step=reheadsLlm])')].map((li) => ({ step: li.dataset.step, state: li.dataset.state,
  status: li.dataset.status, badge: li.querySelector('.dv-flow-status').textContent, no: li.querySelector('.dv-flow-no').textContent,
  name: li.querySelector('.dv-flow-title strong').textContent, text: li.textContent, acts: [...li.querySelectorAll('button')].map((b) => b.textContent) }))"""
CONFIG = "() => { const li = document.querySelector('#taskSteps li[data-step=config]'); return li && { state: li.dataset.state, text: li.textContent, acts: [...li.querySelectorAll('button')].map((b) => b.textContent) }; }"  # 1단계 「구성 확정」(spec_작업 ② §18)
STEP = "(k) => { const li = document.querySelector('#taskSteps li[data-step=' + k + ']'); return li && { state: li.dataset.state, text: li.textContent, acts: [...li.querySelectorAll('button')].map((b) => b.textContent) }; }"  # 줄 하나 — 1단계 「헤딩 · 표 분석」(heads) · 2단계 「헤딩 · 표 다시 분석」(reheads): spec_작업 ② §21
JOURNEY = "() => [...document.querySelectorAll('#taskFlow [data-journey]')].map(b => [b.dataset.journey, b.dataset.state, b.getAttribute('aria-current')])"


def task_of(wid):
    """작업의 task 에서 round 를 뺀 것 — 이 검사는 칸·TASK 를 본다(라운드는 tools/smoke_project_ui.py · tests/test_projects.py, spec_작업 ② §17)."""
    t = next(w for w in requests.get(f"{base}/api/works", timeout=10).json() if w["id"] == wid)["task"]
    return {k: v for k, v in t.items() if k != "round"}


def pick(page, kind, wid, want):
    """첨부 파일 칸에서 문서를 고르고(wid '' = 선택 안 함) 저장 뒤 다시 그려진 칸(새 요소)의 값이 want 가 될 때까지."""
    page.evaluate("() => { document.getElementById('taskFlow').dataset.old = '1'; }")
    page.select_option(f"#taskFlow select[data-task-file={kind}]", wid)
    page.wait_for_function(f"(want) => {{ const f = document.getElementById('taskFlow'); return f && !f.dataset.old && f.dataset.key === taskFlowKey() && JSON.stringify(({SLOTS})()) === JSON.stringify(want); }}", arg=want)

def swap_pick(page, kind, wid, want):
    """지금 문서가 있던 칸에 다른 문서를 고름 — 그 문서가 열리고(작업 개요 = 연구개발과제 내용 그대로) 칸이 want 가 될 때까지."""
    page.select_option(f"#taskFlow select[data-task-file={kind}]", wid)
    page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null && document.getElementById('panel').dataset.tool === 'Div'", arg=wid, timeout=120000)
    page.wait_for_function(f"(want) => {{ const f = document.getElementById('taskFlow'); return f && f.dataset.key === taskFlowKey() && JSON.stringify(({SLOTS})()) === JSON.stringify(want); }}", arg=want)


try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    a, b = upload("기술수요조사서.hwpx"), upload("기술수요조사서.docx")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.add_init_script("try { localStorage.setItem('nfm.toolMore', '1'); } catch (e) {}")  # 패널 머리 오른쪽 묶음(검증·PDF·기록)을 펴 둔다 — 접힘은 smoke_panel_head_ui.py(2026-11-16)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.goto(base)
        page.evaluate("() => { localStorage.setItem('nfm.taskStageOpenR', '1'); localStorage.setItem('nfm.taskStageOpen', '1'); localStorage.setItem('nfm.taskStageOpen2', '1'); }")  # 단계 목록은 「1단계 문서 프레임 작성」 묶음 안(기본 접힘 — spec_작업 ② §14): 이 검사는 세부 목록의 단추를 누르므로 펴 둔다(묶음·한 번에 진행은 tools/smoke_task_run_ui.py)
        open_work(page, a)

        # ---- 1. 국가R&D 양식이 아닌 문서 — 작업 종류 없음 · 탭 없음 · 파일 이름 자리 = 문서 목록
        check("작업 종류 = 선택 안 함(패널 머리의 「작업」 목록 — 상단 바의 옛 #taskKind 는 2026-11-11 없앰)", page.eval_on_selector("#panelTask", "e => e.value") == "" and page.evaluate(VIS, "panelTask")
              and page.locator("#taskKind").count() == 0)
        check("탭 띠에 「연구개발과제」 탭 없음(2026-11-12 없앰) · 패널 머리 탭 「작업 개요」 도 안 보임(「작업 리스트」 는 늘 — ② §17 · 2026-11-16 상단 바 아이콘)", page.locator("#tabDiv").count() == 0
              and page.eval_on_selector("#toolTabTask", "e => e.hidden") and page.evaluate(VIS, "taskListBtn"))
        page.wait_for_function("() => !document.getElementById('docSwitch').hidden")
        opts = page.eval_on_selector_all("#docSwitch option", "os => os.map(o => o.textContent)")
        check("문서 목록 = 지금 문서 + 다른 문서", opts == ["기술수요조사서.hwpx", "기술수요조사서.docx"] and page.eval_on_selector("#docSwitch", "e => e.value") == a
              and page.eval_on_selector("#fileName", "e => e.hidden"), opts)
        page.screenshot(path=str(OUT / "1_none.png"), clip={"x": 0, "y": 0, "width": 1600, "height": 110})

        # ---- 2. 연구개발과제를 고름 — 탭 · 패널 첫 줄(첨부 파일·할 일) · 작업에 저장
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task") and r.request.method == "PUT") as put:
            page.select_option("#panelTask", "rnd")
        check("PUT …/task 200", put.value.status == 200, put.value.status)
        try:  # 저장 뒤 작업 목록을 다시 읽고 나서 그 내용으로 간다(taskSetNow → panelTaskPick) — PUT 응답 직후엔 아직
            page.wait_for_function("() => document.getElementById('panel').dataset.tool === 'Div'", timeout=30000)
        except Exception:
            pass
        check("고르면 그 내용이 바로 열림 — 탭 띠에 탭은 안 생기고 활성 탭도 없음", page.get_attribute("#panel", "data-tool") == "Div" and page.locator("#tabDiv").count() == 0
              and page.locator("#workspaceNav .tab.active").count() == 0 and page.get_attribute("#toolTabTask", "aria-selected") == "true", page.get_attribute("#panel", "data-tool"))
        page.wait_for_selector("#divMarksBar")
        check("패널 제목 「작업 개요」 · 꼬리표 「프로젝트 · 워크플로우」(2026-11-12 ② §17 — 접힌 띠 이름)", page.eval_on_selector("#toolTitle", "e => e.textContent.trim()") == "작업 개요"
              and page.eval_on_selector("#toolTag", "e => e.textContent.trim()") == "프로젝트 · 워크플로우",
              page.eval_on_selector("#toolTitle", "e => e.textContent") + " / " + page.eval_on_selector("#toolTag", "e => e.textContent"))
        labels = page.evaluate("() => { const b = document.getElementById('divBox'); return b.firstElementChild.classList.contains('dv-task') ? [...b.querySelectorAll('.dv-task-field > span')].map((s) => s.textContent) : null; }")
        check("패널 첫 카드 = 프로젝트 · 워크플로우 · 첨부 파일(「작업」 칸은 패널 머리에만 — 2026-11-12 · 프로젝트가 먼저 ② §17)", labels == ["프로젝트", "워크플로우", "첨부 파일"]
              and page.locator("#divBox .dv-task select[data-task=kind]").count() == 0 and page.input_value("#panelTask") == "rnd", labels)
        # 2026-11-12 — 이관이 아니면 과제 구성 입력(단계·차년도 · 기관 구성 …)은 전처럼 패널에 바로 · 표시 줄 이름 = 「구분 기준 자리 표시」(처음엔 「문서 표시」 — 사용자 "뭘 이야기 하는지 모르겠다")
        # 2026-11-14 — 묶음 없는 TASK 는 구성 입력도 실행 묶음(카드 하나)의 접어 둔 「세부」 안(spec_구분_기준 ② §22 「카드 하나」 — 사용자 "한번에 진행, 불러오기 2개 메뉴가 있고, 다른 것은 접혀있어야 하고")
        check("이관이 아니면 과제 구성 입력은 실행 묶음의 접어 둔 「세부」 안(1단계 묶음 안의 칸 없음 · 패널에 따로 없음)", page.locator("#divBox > #divRunBar > #divRunMore fieldset.dv-config").count() == 1 and page.locator("#divBox > fieldset.dv-config").count() == 0
              and page.locator("#divBox > #divAppliedState").count() == 1 and page.locator("#taskFrameForm").count() == 0
              and page.evaluate("() => !document.getElementById('divRunMore').open && document.getElementById('divRunAll').classList.contains('primary') && !document.getElementById('divPlanButton').classList.contains('primary')"))
        # 2026-11-13 실행 묶음(spec_구분_기준 ② §22) — 첫 카드 바로 다음, 그 아래 문서 반영 상태. 보이는 것은 「한 번에 진행」 · 「불러오기」 둘, 「① 변경 계획 보기 › ② 반영 · 계획 다시 열기」 는 「세부」 안. 전체 흐름은 tools/smoke_div_run_ui.py
        run = page.evaluate("""() => { const k = [...document.getElementById('divBox').children], all = [...document.querySelectorAll('#divRunBar button:not(.panel-help)')]; return { order: k.slice(0, 3).map((e) => e.id || e.className.split(' ')[0]),
          seen: all.filter((b) => b.checkVisibility()).map((b) => b.textContent), steps: [...document.querySelectorAll('#divRunMore .dv-run-steps button')].map((b) => b.textContent), off: [...document.querySelectorAll('#divRunBar button:disabled')].map((b) => b.id) }; }""")
        check("실행 묶음 — 첫 카드 다음 · 보이는 단추는 「한 번에 진행」 · 「불러오기」 · 차례 단추 셋은 접어 둔 「세부」 안 · 계획이 없으면 반영·다시 열기 꺼짐", run["order"] == ["dv-task", "divRunBar", "divAppliedState"]
              and run["seen"] == ["한 번에 진행", "불러오기"] and run["steps"] == ["① 변경 계획 보기", "② 반영", "계획 다시 열기"] and {"divApplyButton", "divReopenPlan"} <= set(run["off"]), run)
        check("표시 줄 이름 「구분 기준 자리 표시」 · 부가 설명은 노트", page.inner_text("#divMarksBar .dv-marks-copy strong").strip() == "구분 기준 자리 표시"
              and "단계·차년도·기관이 걸린 자리를 색으로" in page.get_attribute("#divMarksBar .dv-marks-copy .panel-help", "data-help")
              and page.locator("#divMarksBar .dv-marks-copy .dv-caption").count() == 0, page.inner_text("#divMarksBar .dv-marks-copy"))
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task")):
            page.select_option("#divBox .dv-task select[data-task=file]", "report")
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task")):
            page.select_option("#divBox .dv-task select[data-task=job]", "plan_to_report")
        saved = next(w for w in requests.get(f"{base}/api/works", timeout=10).json() if w["id"] == a)["task"]
        check("작업에 저장(TASK 를 고르면 화면은 round 를 안 보내고 서버가 정한다 — 묶음에 작업이 없으면 1: ② §10)", {k: v for k, v in saved.items() if k != "round"} == {"kind": "rnd", "file": "report", "job": "plan_to_report", "project": ""}
              and saved.get("round", 1) == 1, saved)
        # 이관을 고르면 첨부 파일 칸 둘 + 단계 목록(② §11) — 과제 이름이 없으면 고를 문서는 지금 문서뿐, 첫 단계가 「지금」
        page.wait_for_selector("#taskFlow #taskSteps li[data-step=files]")
        check("이관 — 첨부 파일 칸 둘(사업계획서 = 기준 · 연차보고서)", page.evaluate(SLOTS) == {"plan": "", "report": a}
              and page.eval_on_selector_all("#taskFlow .dv-flow-files label > span", "xs => xs.map(x => x.textContent)") == ["사업계획서(기준)", "연차보고서"]
              and page.locator("#divBox .dv-task select[data-task=file]").count() == 0, page.evaluate(SLOTS))
        opts = page.eval_on_selector_all("#taskFlow select[data-task-file=plan] option", "os => os.map(o => o.textContent)")
        check("과제 이름이 없으면 칸의 목록 = 지금 문서뿐", opts == ["선택 안 함", "기술수요조사서.hwpx — 지금 문서 (연차보고서)"], opts)
        st = page.evaluate(STEPS)
        check("준비는 다음 작업 · ①~④ 대기 · ⑤ 준비 중(순서와 상태를 따로 표시)", [s["state"] for s in st] == ["now", "todo", "todo", "todo", "todo", "soon", "todo"] and "사업계획서를 위 칸에서 고르세요" in st[0]["text"]
              and "프로젝트 이름을 적으면" in st[0]["text"] and [s["name"] for s in st[1:]] == ["프로젝트 구성 반영", "자리 연결", "표 안 연결 · 넣기 계획", "내용 반영", "합계 계산 → 결과 확인", "작성요령 삭제"]
              and [s["no"] for s in st] == ["·", "①", "②", "③", "④", "⑤", "⑥"] and [s["badge"] for s in st] == ["다음 작업", "대기", "대기", "대기", "대기", "준비 중", "대기"]
              and [s["step"] for s in st] == ["files", "division", "link", "plan", "apply", "later", "guide"], st)
        check("TASK 순서 — 준비가 현재 · 문서 검토 · 구성 맞추기 · 내용 넣기 · 문서 정리는 대기(묶음 넷 — spec_작업 ② §21)", page.evaluate(JOURNEY) == [["prepare", "now", "step"], ["review", "todo", None], ["frame", "todo", None], ["map", "todo", None], ["clean", "todo", None]], page.evaluate(JOURNEY))
        page.click('#taskFlow [data-journey="prepare"]')
        check("준비 길찾기 — 첫 문서 선택칸으로 키보드 초점", page.evaluate("() => document.activeElement === document.querySelector('#taskFlow select[data-task-file=plan]')"))
        page.evaluate("() => { document.getElementById('taskStage2').open = false; }")
        before_journey = requests.get(f"{base}/api/docs/{a}", timeout=10).json().get("rev")
        page.click('#taskFlow [data-journey="map"]')
        check("대기 단계 길찾기 — 세부 목록만 열고 실행은 계속 꺼짐", page.evaluate("() => document.getElementById('taskStage2').open && document.activeElement === document.querySelector('#taskStage2 > summary') && document.querySelector('#taskStage2 [data-task-run]').disabled")
              and requests.get(f"{base}/api/docs/{a}", timeout=10).json().get("rev") == before_journey)
        page.evaluate("() => { document.getElementById('taskStage').open = false; }")
        page.locator('#taskStage > summary .panel-help').click()
        check("프레임 노트 — 설명은 툴팁에 · 노트를 눌러도 묶음은 접힌 채", page.locator('#panelHelpTooltip').is_visible() and "구조만" in page.inner_text('#panelHelpTooltip') and not page.eval_on_selector('#taskStage', 'e => e.open'))
        page.keyboard.press('Escape')
        page.evaluate("() => { document.getElementById('taskStage').open = true; }")
        # 2026-11-12 사용자 "1단계에서는 단계, 차년도, 기관구성이 들어가야 하지 … UI가 너무 떨어져 있네": 이관이면 과제 구성 입력이 1단계 묶음 안(세부 목록 아래 #taskFrameForm)
        check("이관 — 구성 입력 · 문서 반영 상태·변경 계획이 2단계 「구성 맞추기」 묶음 안(입력 → 반영 차례 — §21: 전의 1단계 묶음 #taskStage0 은 없다) · 패널에는 없음 · 「변경 계획 보기」 는 강조 아님", page.evaluate("""() => {
          const f = document.getElementById('taskFrameForm'), a = document.getElementById('taskFrameApply'), s = document.getElementById('taskStage');
          return !!f && f.parentElement === s && !document.getElementById('taskStage0') && f.previousElementSibling.matches('ol.dv-flow-steps') && a.previousElementSibling === f
            && [...document.querySelectorAll('#taskSteps > details')].map((d) => d.dataset.stage).join() === 'review,frame,map,clean' && f.querySelectorAll('fieldset.dv-config .dv-card').length === 2 && !!f.querySelector('#divSourceSel')
            && !!a && a.parentElement === s && !!a.querySelector('#divAppliedState') && !!a.querySelector('#divRunBar #divPlanButton') && !!a.querySelector('#divRunBar #divApplyButton') && !a.querySelector('#divRunAll') && !document.querySelector('#divBox > fieldset.dv-config, #divBox > #divAppliedState, #divBox > #divRunBar')
            && !document.getElementById('divPlanButton').classList.contains('primary') && [...document.querySelectorAll('#taskSteps li')].map((li) => li.dataset.step).join() === 'files,heads,headsLlm,config,division,reheads,reheadsLlm,link,plan,apply,later,guide'; }"""))
        check("⑤ 합계 계산 줄 — 아직 없는 단계라는 글(상태는 「준비 중」 그대로)", "아직 없는 단계입니다" in st[5]["text"] and "계산 칸" in st[5]["text"] and st[5]["badge"] == "준비 중", st[5])
        page.screenshot(path=str(OUT / "2_rnd.png"))
        NOLAP = """() => { const t = document.querySelector('.topbar'), r = [...t.children].filter((e) => e.getClientRects().length && !e.classList.contains('spacer')).map((e) => e.getBoundingClientRect());
            return t.scrollWidth <= t.clientWidth + 1 && r.every((x, i) => i === 0 || x.left >= r[i - 1].right - 1) && document.getElementById('fileInfo').scrollWidth <= document.getElementById('fileInfo').clientWidth + 1; }"""
        for width in (1600, 1280, 1100):
            page.set_viewport_size({"width": width, "height": 800})
            page.wait_for_timeout(300)
            check(f"상단 바 넘침·겹침 없음({width}px)", page.evaluate(NOLAP))
            page.screenshot(path=str(OUT / f"3_top_{width}.png"), clip={"x": 0, "y": 0, "width": width, "height": 60})
        page.set_viewport_size({"width": 1600, "height": 900})
        page.locator("#panel").screenshot(path=str(OUT / "4_panel.png"))

        # ---- 3. 새로 고쳐도 그대로
        open_work(page, a)
        check("새로 연 화면(검증)에 패널 머리 탭 「작업 개요」 · 「검증」(고름)", page.evaluate(VIS, "toolTabs") and page.inner_text("#toolTabTask").strip() == "작업 개요"
              and page.get_attribute("#tabVerify", "aria-selected") == "true", page.inner_text("#toolTabs"))  # 「검증」 은 패널 머리의 고정 탭(2026-11-15)
        page.click("#toolTabTask")
        page.wait_for_selector("#divBox .dv-task select")
        vals = page.evaluate("() => [document.getElementById('panelTask').value, document.querySelector('#divBox .dv-task select[data-task=job]').value]")
        check("새로 고친 뒤 그대로", vals == ["rnd", "plan_to_report"] and page.evaluate(SLOTS) == {"plan": "", "report": a}, [vals, page.evaluate(SLOTS)])

        # ---- 4. 선택을 풀면 탭이 사라지고 「검증」 으로
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task")):
            page.select_option("#panelTask", "")
        check("패널 머리 탭 「작업 개요」 사라짐 · 검증 탭으로", page.eval_on_selector("#toolTabTask", "e => e.hidden") and page.get_attribute("#panel", "data-tool") == "Verify",
              page.get_attribute("#panel", "data-tool"))
        check("오른쪽 단추 메뉴에 구분 기준 항목 없음", page.evaluate("() => divCtxItems({ target: document.querySelector('#doc .para[data-id]') }).length") == 0)
        page.select_option("#panelTask", "rnd")
        check("다시 고르면 첨부 파일·할 일 그대로", page.evaluate("() => state.task.file + '/' + state.task.job") == "report/plan_to_report")

        # ---- 5. 문서 목록으로 다른 문서 열기 — 목록의 앞 문서에는 첨부 파일·할 일 꼬리
        page.select_option("#docSwitch", b)
        page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .para') != null", arg=b, timeout=60000)
        page.wait_for_function("(id) => !document.getElementById('docSwitch').hidden && document.getElementById('docSwitch').value === id", arg=b)
        opts = page.eval_on_selector_all("#docSwitch option", "os => os.map(o => o.textContent)")
        check("다른 문서로 바뀜 · 목록에 앞 문서(종류·할 일)", opts[0] == "기술수요조사서.docx" and opts[1] == "기술수요조사서.hwpx · 연차보고서 · 사업계획서 → 연차보고서 이관", opts)
        page.screenshot(path=str(OUT / "5_switched.png"), clip={"x": 0, "y": 0, "width": 1600, "height": 110})

        # ---- 6. 과제 묶음 — 같은 과제 이름의 문서끼리: 들어온 문서는 과제의 할 일을 따르고, 문서 목록은 그 과제의 문서만
        c = upload("기술수요조사서.hwpx")
        open_work(page, a)
        page.click("#toolTabTask")
        page.wait_for_selector("#divBox .dv-task .dv-task-field input")
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task")):
            page.fill("#divBox .dv-task .dv-task-field input", "  시험   과제 ")  # 과제 칸의 입력(1단계 묶음 안의 과제 구성 입력과 가름 — 2026-11-12)
            page.keyboard.press("Enter")
        page.wait_for_function("() => state.task.project === '시험 과제'")
        # 2026-11-12 ② §17: 프로젝트 안 TASK 는 여럿 — 프로젝트 이름만 같으면 TASK 를 옮겨 오지 않는다(옛 「과제의 할 일 전파」 폐기). 같은 TASK·라운드로 넣어야 한 묶음
        alone = requests.put(f"{base}/api/works/{c}/task", json={"kind": "rnd", "file": "plan", "job": "", "project": "시험 과제"}, timeout=10).json()["task"]
        check("프로젝트에 들어와도 TASK 는 옮겨 오지 않음(전파 없음 — ② §17)", alone["job"] == "" and alone["project"] == "시험 과제", alone)
        joined = requests.put(f"{base}/api/works/{c}/task", json={"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": "시험 과제", "round": 1}, timeout=10).json()["task"]
        check("같은 프로젝트·TASK·라운드로 넣은 문서", joined == {"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": "시험 과제", "round": 1}, joined)
        open_work(page, a)
        page.wait_for_function("() => !document.getElementById('docSwitch').hidden")
        opts = page.eval_on_selector_all("#docSwitch option", "os => os.map(o => o.textContent)")
        check("문서 목록 = 같은 과제의 문서만 · 목적 문서(이관의 연차보고서)는 이름 뒤에 과제 이름(② §10)", opts == ["기술수요조사서_시험 과제.hwpx", "기술수요조사서.hwpx · 사업계획서 · 사업계획서 → 연차보고서 이관"], opts)
        page.click("#toolTabTask")
        page.wait_for_function(f"(c) => ({SLOTS})().plan === c", arg=c)
        check("패널 첫 줄에 과제 이름 · 같은 과제의 사업계획서가 칸에(따로 「같은 과제 문서」 줄 없음)", page.input_value("#divBox .dv-task .dv-task-field input") == "시험 과제"
              and page.evaluate(SLOTS) == {"plan": c, "report": a} and page.locator("#divBox .dv-task-mates").count() == 0, page.evaluate(SLOTS))
        # 2026-11-13 ② §19 — 프로젝트 고르기 목록: 브라우저 datalist(#taskProjects — 지금 적힌 글자와 맞는 이름만 보였다) 대신 자체 목록(#taskProjectList). 칸에 「시험 과제」 가 적혀 있어도 모든 프로젝트가 보인다
        PROJ = "#divBox .dv-task input[data-task=project]"
        OPTS = "() => [...document.querySelectorAll('#taskProjectList [role=option]')].map((o) => ({ name: o.dataset.project, fresh: !!o.dataset.projectNew, text: o.textContent, tags: [...o.querySelectorAll('.project-combo-tag')].map((t) => t.textContent) }))"
        x = upload("기술수요조사서.hwpx")  # 다른 프로젝트의 문서 하나(TASK 없음) — 이 묶음이 끝나면 지운다
        requests.put(f"{base}/api/works/{x}/task", json={"kind": "rnd", "file": "", "job": "", "project": "다른 과제"}, timeout=10).raise_for_status()
        page.evaluate("() => loadWorks()")
        page.wait_for_function("(x) => worksList.some((w) => w.id === x && (w.task || {}).project === '다른 과제')", arg=x)
        check("프로젝트 칸 — datalist 없음 · role=combobox · 닫힘", page.locator("#taskProjects").count() == 0 and page.get_attribute(PROJ, "list") is None and page.get_attribute(PROJ, "role") == "combobox"
              and page.get_attribute(PROJ, "aria-expanded") == "false" and page.get_attribute(PROJ, "aria-controls") == "taskProjectList" and page.locator("#taskProjectList").count() == 0)
        page.focus(PROJ)
        check("포커스만으로는 목록이 열리지 않음", page.evaluate("() => document.activeElement === document.querySelector('#divBox .dv-task input[data-task=project]')") and page.locator("#taskProjectList").count() == 0
              and page.get_attribute(PROJ, "aria-expanded") == "false")
        page.click(PROJ)
        page.wait_for_selector("#taskProjectList[role=listbox]")
        page.wait_for_function("() => document.querySelectorAll('#taskProjectList .project-combo-tag[data-division]').length === 2")  # 구분 기준 표지는 GET /api/projects 가 온 뒤에
        opts = page.evaluate(OPTS)
        check("칸을 누르면 모든 프로젝트 — 지금 적힌 값(「시험 과제」)으로 거르지 않음 · 지금 프로젝트가 맨 앞", [o["name"] for o in opts] == ["시험 과제", "다른 과제"] and page.input_value(PROJ) == "시험 과제"
              and page.get_attribute(PROJ, "aria-expanded") == "true", opts)
        check("줄마다 구분 기준 표지 · 지금 프로젝트에 「지금」", opts[0]["tags"] == ["프로젝트 구성 없음", "지금"] and opts[1]["tags"] == ["프로젝트 구성 없음"], opts)
        check("목록은 패널에 잘리지 않음(body 에 고정 위치 · 칸 바로 아래 · 창 안)", page.evaluate("""() => { const l = document.getElementById('taskProjectList'), r = l.getBoundingClientRect(), i = document.querySelector('#divBox .dv-task input[data-task=project]').getBoundingClientRect();
          return l.parentElement === document.body && getComputedStyle(l).position === 'fixed' && r.top >= i.bottom && r.top - i.bottom < 8 && r.right <= innerWidth && r.bottom <= innerHeight && r.height > 20; }"""))
        page.locator("#panel").screenshot(path=str(OUT / "6_project_list.png"))
        page.fill(PROJ, "다른")
        opts = page.evaluate(OPTS)
        check("글자를 고치면 그 글자가 든 이름만 + 끝 줄 「「글」 새 프로젝트로」", [(o["name"], o["fresh"]) for o in opts] == [("다른 과제", False), ("다른", True)] and opts[1]["text"] == "「다른」 새 프로젝트로", opts)
        page.keyboard.press("Escape")
        check("Esc — 목록 닫힘 · 값 되돌림 · 저장 안 함", page.locator("#taskProjectList").count() == 0 and page.input_value(PROJ) == "시험 과제" and page.get_attribute(PROJ, "aria-expanded") == "false"
              and page.evaluate("() => state.task.project") == "시험 과제" and task_of(a)["project"] == "시험 과제")
        page.keyboard.press("ArrowDown")  # ↓ = 열기(모두 보임) → ↓ ↓ = 둘째 줄
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        check("키보드 — ↓ 로 열고 옮김(aria-activedescendant · aria-selected)", page.get_attribute(PROJ, "aria-activedescendant") == "taskProjectList-opt-1"
              and page.eval_on_selector_all("#taskProjectList [role=option]", "os => os.map(o => o.getAttribute('aria-selected'))") == ["false", "true"]
              and page.evaluate("() => document.activeElement === document.querySelector('#divBox .dv-task input[data-task=project]')"))
        page.evaluate("() => { window.keptProject = document.querySelector('#divBox .dv-task input[data-task=project]'); divRender(); }")  # 패널을 다시 그려도(칸이 새로 만들어짐) 포커스·열린 목록이 새 칸으로
        check("패널을 다시 그려도 포커스·열린 목록·고른 줄 그대로", page.evaluate("""() => { const i = document.querySelector('#divBox .dv-task input[data-task=project]');
          return i !== window.keptProject && document.activeElement === i && i.getAttribute('aria-expanded') === 'true' && i.getAttribute('aria-activedescendant') === 'taskProjectList-opt-1' && document.querySelectorAll('#taskProjectList').length === 1; }"""))
        page.mouse.click(5, 400)  # 바깥(문서 쪽)을 누르면 닫힘
        check("바깥을 누르면 닫힘 · 고르지 않음", page.locator("#taskProjectList").count() == 0 and page.evaluate("() => state.task.project") == "시험 과제")
        # 고르면 저장 — 다른 프로젝트의 문서(x)를 열어 「시험 과제」 를 고른다(그 프로젝트에 구분 기준이 없으니 알림 「… 구분 기준이 없습니다 — 새로 만드세요」 · 줄 「구분 기준 없음」 + 「새로 만들기」)
        open_work(page, x)
        page.click("#toolTabTask")
        page.wait_for_selector(PROJ)
        page.click(PROJ)
        page.wait_for_selector("#taskProjectList [role=option]")
        check("다른 프로젝트의 문서에서도 모든 프로젝트(지금 프로젝트가 앞)", [o["name"] for o in page.evaluate(OPTS)] == ["다른 과제", "시험 과제"], page.evaluate(OPTS))
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{x}/task") and r.request.method == "PUT") as put:
            page.locator("#taskProjectList [role=option]", has_text="시험 과제").click()
        page.wait_for_function("() => state.task.project === '시험 과제' && !!document.querySelector('#divBox .project-sharing[data-division=none]') && !document.getElementById('toast').hidden")
        check("줄을 고르면 그 프로젝트로 저장(PUT …/task — round 는 안 보냄: 서버가 그 TASK 의 최신 라운드로, 없으면 1)", put.value.status == 200 and put.value.json()["task"]["project"] == "시험 과제"
              and "round" not in put.value.request.post_data_json and put.value.json()["task"].get("round", 1) == 1 and page.evaluate("() => taskRound()") == 1
              and task_of(x)["project"] == "시험 과제" and page.locator("#taskProjectList").count() == 0, (put.value.request.post_data_json, put.value.json()))
        check("들어간 직후 알림 — 서버가 알려 준 갈래(division: none) = 그 프로젝트에 구분 기준이 없음", put.value.json().get("division") == "none"
              and "프로젝트 「시험 과제」 에 구성이 없습니다 — 새로 만드세요" in page.inner_text("#toast"), (put.value.json().get("division"), page.inner_text("#toast")))
        check("프로젝트 칸 아래 「구분 기준 없음」 줄 + 「새로 만들기」", "프로젝트 구성 없음" in page.inner_text("#divBox .project-sharing") and page.locator("#divBox .project-sharing [data-division-new]").is_visible(), page.inner_text("#divBox .project-sharing"))
        page.click("#divBox .project-sharing [data-division-new]")
        check("「새로 만들기」 — 실행 묶음의 「세부」 를 펴고 구성 「불러오기」 목록으로 포커스(양식 묶음이 없는 문서)", page.evaluate("() => { const c = document.querySelector('#divBox fieldset.dv-config'), m = document.getElementById('divRunMore'); return !!c && !!m && m.open && c.checkVisibility() && document.activeElement === document.getElementById('divSourceSel'); }"))
        # 값이 있는 문서가 구분 기준 없는 프로젝트에 들어감 → division: seeded 「이 문서의 구성을 올렸습니다」. 「시험 과제」 에는 값을 남기지 않게(뒤 6-2 가 「값 없음」 에서 시작) x 를 프로젝트에서 빼고 값을 넣은 뒤 새 이름으로 들어간다
        requests.put(f"{base}/api/works/{x}/task", json={"kind": "rnd", "file": "", "job": "", "project": ""}, timeout=10).raise_for_status()
        requests.put(f"{base}/api/docs/{x}/divisions/settings", json={"values": {"stages": [2], "orgs": {"lead": "올린 기관", "joint": []}}}, timeout=30).raise_for_status()
        open_work(page, x)
        page.click("#toolTabTask")
        page.wait_for_selector(PROJ)
        page.wait_for_function("() => !!dv.view && !!dv.view.settings && state.task.project === ''")
        check("프로젝트가 없는 문서 — 구분 기준 줄·버전 줄 없음", page.locator("#divBox .project-sharing").count() == 0 and page.locator("#divBox .project-versions").count() == 0)
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{x}/task") and r.request.method == "PUT") as put:
            page.fill(PROJ, "셋째 과제")   # 글자를 치면 목록이 열리고(끝 줄 「새 프로젝트로」) Enter 는 적은 글 그대로
            page.keyboard.press("Enter")
        page.wait_for_function("() => state.task.project === '셋째 과제' && !!document.querySelector('#divBox .project-sharing[data-division=has]') && document.getElementById('toast').textContent.includes('올렸습니다')")
        seeded = requests.get(f"{base}/api/docs/{x}/divisions", timeout=30).json()
        check("값이 있는 문서가 빈 프로젝트에 들어감 — division: seeded · 알림 · 「구분 기준 있음 … 프로젝트 공유」", put.value.json().get("division") == "seeded" and "round" not in put.value.request.post_data_json
              and "프로젝트 「셋째 과제」 에 구성이 없어 이 문서의 구성을 올렸습니다 — 확인한 뒤 「프로젝트에 저장」" in page.inner_text("#toast")
              and seeded["projectSharing"]["shared"] and seeded["settings"]["values"]["orgs"]["lead"] == "올린 기관"
              and "프로젝트 구성 있음" in page.inner_text("#divBox .project-sharing") and "프로젝트 공유" in page.inner_text("#divBox .project-sharing"), (put.value.json(), page.inner_text("#toast")))
        open_work(page, a)  # 뒤 검사는 a(연차보고서) · c(사업계획서)로 잇는다 — x 는 지운다
        requests.delete(f"{base}/api/works/{x}", timeout=30).raise_for_status()
        page.click("#toolTabTask")
        page.wait_for_selector("#taskFlow")
        page.evaluate("() => loadWorks().then(() => { divRender(); taskFlowLoad(); })")  # 지운 문서가 화면의 작업 목록에 남지 않게
        page.wait_for_function(f"([c, x]) => {{ const f = document.getElementById('taskFlow'); return f && f.dataset.key === taskFlowKey() && !worksList.some((w) => w.id === x) && ({SLOTS})().plan === c; }}", arg=[c, x])
        page.locator("#panel").screenshot(path=str(OUT / "6_panel_project.png"))

        # ---- 6-1. 첨부 파일 칸 바꾸기(② §11) — 고른 문서는 과제의 그 종류가 되고, 칸에 있던 다른 문서는 과제에서 나온다(지금 문서는 종류만 비움)
        pick(page, "plan", "", {"plan": "", "report": a})
        check("「선택 안 함」 — 그 문서는 과제에서 나옴(종류는 그대로)", task_of(c) == {"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": ""}, task_of(c))
        pick(page, "plan", c, {"plan": c, "report": a})
        check("과제 없는 문서를 고름 — 과제에 들어옴", task_of(c)["project"] == "시험 과제" and task_of(c)["file"] == "plan", task_of(c))
        # 2026-11-12 사용자 "연차보고서는 빈건데 왜 화면에 보이는 것은 1단계가 진행된 문서로 나오냐?" — 지금 문서가 있던 칸에 다른 문서가 들어오면 그 문서를 열고, 지금 문서는 다른 문서처럼 과제에서 나온다
        swap_pick(page, "report", c, {"plan": "", "report": c})
        check("지금 문서의 칸에 다른 문서 — 그 문서가 열리고(작업 개요 그대로) 옛 문서는 과제에서 나옴(종류는 그대로)", task_of(a) == {"kind": "rnd", "file": "report", "job": "plan_to_report", "project": ""}
              and task_of(c) == {"kind": "rnd", "file": "report", "job": "plan_to_report", "project": "시험 과제"} and page.evaluate("() => state.task.file + '/' + state.task.project") == "report/시험 과제"
              and page.get_attribute("#panel", "data-tool") == "Div", [task_of(a), task_of(c), page.get_attribute("#panel", "data-tool")])
        page.wait_for_function("() => !document.getElementById('docSwitch').hidden || !document.getElementById('fileName').hidden")
        check("열린 문서 = 목적 문서 — 상단 바 이름 뒤에 과제 이름 · 문서 목록에 옛 문서 없음", page.evaluate("() => state.name") == "기술수요조사서_시험 과제.hwpx"
              and page.eval_on_selector_all("#docSwitch option", "os => os.map(o => o.value)") in ([], [c]), [page.evaluate("() => state.name"), page.eval_on_selector_all("#docSwitch option", "os => os.map(o => o.textContent)")])
        swap_pick(page, "report", a, {"plan": "", "report": a})
        check("옛 문서를 다시 고름 — 그 문서가 열리고 칸에 있던 문서는 과제에서 나옴", task_of(a)["file"] == "report" and task_of(a)["project"] == "시험 과제" and task_of(c)["project"] == "", [task_of(a), task_of(c)])
        # 칸 오른쪽 폴더 단추로 올림 — 지금 문서(연차보고서)가 그 칸의 문서면 올린 문서로 화면이 바뀐다 · 사업계획서 칸에 올리면(지금 문서는 연차보고서) 화면은 그대로
        tip = page.get_attribute("#taskFlow [data-task-up=report]", "title")
        with page.expect_file_chooser() as fc:
            page.click("#taskFlow [data-task-up=report]")
        fc.value.set_files(str(ROOT / "samples" / "기술수요조사서.hwpx"))
        page.wait_for_function("(a) => state.id && state.id !== a && document.querySelector('#doc .sheet .para') != null && document.getElementById('panel').dataset.tool === 'Div'", arg=a, timeout=120000)
        d = page.evaluate("() => state.id")
        page.wait_for_function(f"(d) => {{ const f = document.getElementById('taskFlow'); return f && f.dataset.key === taskFlowKey() && ({SLOTS})().report === d; }}", arg=d)
        check("연차보고서를 보며 연차보고서 칸에 올림 — 올린 문서(새 작업)가 열리고 칸에 들어감 · 옛 문서는 과제에서 나옴 · 이름 뒤에 과제 이름", d not in (a, b, c)
              and task_of(d) == {"kind": "rnd", "file": "report", "job": "plan_to_report", "project": "시험 과제"} and task_of(a) == {"kind": "rnd", "file": "report", "job": "plan_to_report", "project": ""}
              and page.evaluate("() => state.name") == "기술수요조사서_시험 과제.hwpx" and "올린 문서로 화면이 바뀌고" in tip, [d, task_of(d), task_of(a), page.evaluate("() => state.name"), tip])
        tip = page.get_attribute("#taskFlow [data-task-up=plan]", "title")
        with page.expect_file_chooser() as fc:
            page.click("#taskFlow [data-task-up=plan]")
        fc.value.set_files(str(ROOT / "samples" / "기술수요조사서.hwpx"))
        page.wait_for_function(f"() => {{ const f = document.getElementById('taskFlow'); return f && f.dataset.key === taskFlowKey() && !!({SLOTS})().plan; }}", timeout=120000)
        e = page.evaluate(SLOTS)["plan"]
        check("연차보고서를 보며 사업계획서 칸에 올림 — 화면은 그대로(올린 문서는 칸에만)", page.evaluate("() => state.id") == d and task_of(e)["file"] == "plan" and task_of(e)["project"] == "시험 과제"
              and "지금 보는 문서는 그대로" in tip, [page.evaluate("() => state.id"), task_of(e), tip])
        for wid in (d, e):  # 뒤 검사는 a(연차보고서) · c(사업계획서)로 잇는다 — 올린 둘은 지운다
            if wid == d:
                swap_pick(page, "report", a, {"plan": e, "report": a})
                page.wait_for_function("() => !state.polling", timeout=60000)   # 옛 문서(d)의 검증 읽기가 끝난 뒤에 지운다 — 지운 뒤 도착한 읽기가 404 를 콘솔에 남긴다
            requests.delete(f"{base}/api/works/{wid}", timeout=30).raise_for_status()
        page.evaluate("() => loadWorks().then(() => { divRender(); taskFlowLoad(); })")
        page.wait_for_function(f"() => {{ const f = document.getElementById('taskFlow'); return f && f.dataset.key === taskFlowKey() && JSON.stringify(({SLOTS})()) === JSON.stringify({{plan: '', report: '{a}'}}); }}")
        pick(page, "plan", a, {"plan": a, "report": ""})
        pick(page, "report", a, {"plan": "", "report": a})
        check("지금 문서를 다른 칸으로 옮겼다 되돌림", task_of(a)["file"] == "report" and page.evaluate("() => state.task.file") == "report", task_of(a))
        pick(page, "plan", c, {"plan": c, "report": a})

        # ---- 6-2. 단계(② §11) — ① 구분 기준 확인: 사업계획서가 기준. 값 없음 → 다름(맞추기) → 같음·반영 전 → 반영됨 → ② 자리 연결(먼저 헤딩·표 분석)
        page.wait_for_function(f"() => {{ const c = ({CONFIG})(); return !!c && c.text.includes('프로젝트 구성(단계·차년도·기관)이 없습니다'); }}")
        st, cf = page.evaluate(STEPS), page.evaluate(CONFIG)
        check("구성 확정 — 사업계획서에 값 없음 → 「사업계획서에서 추출」(분석이 없어 1단계가 지금이어도 누를 수 있다 = 진행 가능) · ① 은 대기(확정 뒤)", cf["state"] == "ready" and cf["acts"] == ["사업계획서에서 추출", "구성 불러오기"]   # 「구성 불러오기」 = 2단계의 선택 단계(파일 · 저장된 곳 — §21)
              and [s["state"] for s in st][:6] == ["done", "todo", "todo", "todo", "todo", "soon"] and not st[1]["acts"], (cf, st))
        hd = page.evaluate(STEP, "heads")
        check("1단계 「헤딩 · 표 분석」 이 지금 — 두 문서에 분석 없음 · 「분석」(강조 · 스크립트)", hd["state"] == "now" and "사업계획서 없음 · 연차보고서 없음" in hd["text"] and hd["acts"] == ["분석"]
              and page.evaluate("() => document.querySelector('#taskSteps li[data-step=heads] button').classList.contains('primary')"), hd)
        plan_values = {"stages": [2, 1], "orgs": {"lead": "가 기관", "joint": ["나 기관"]}, "current": 2}
        requests.put(f"{base}/api/docs/{c}/divisions/settings", json={"values": plan_values}, timeout=30).raise_for_status()
        conf = requests.post(f"{base}/api/docs/{c}/divisions/confirm", json={}, timeout=30).json()["confirmed"]   # 1단계 — 프로젝트에 확정(spec_작업 ② §18)
        check("「구성 확정」(API) — 프로젝트 「시험 과제」 에 확정 · 유효", conf and conf["scope"] == "project" and conf["project"] == "시험 과제" and conf["valid"], conf)
        # 2026-11-12 ② §17: 같은 프로젝트·TASK·라운드의 문서는 구분 기준 값을 공유한다 — 사업계획서에 값을 넣으면 연차보고서도 같은 값(옛 「다름 → 사업계획서 기준으로 맞추기」 를 거치지 않는다)
        sv = requests.get(f"{base}/api/docs/{a}/divisions", timeout=30).json()["settings"]["values"]
        check("사업계획서에 값을 넣으면 같은 라운드의 연차보고서도 같은 값(프로젝트 공유 — 당해 차년도도)", [sv["stages"], sv["orgs"]["lead"], sv["orgs"]["joint"], sv.get("current")] == [[2, 1], "가 기관", ["나 기관"], 2], sv)
        page.evaluate("(id) => openWork(id)", c)   # 사업계획서를 고치는 중 — ① 도 같은 값(맞추기 단추 없음)
        page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=c, timeout=120000)
        page.evaluate("() => showTab('Div')")
        page.wait_for_function(f"() => {{ const s = ({STEPS})()[1]; return !!s && s.text.includes('값은 사업계획서와 같음'); }}")
        st = page.evaluate(STEPS)
        check("사업계획서를 고치는 중 — ① 값 같음 · 「사업계획서 기준으로 맞추기」 없음", "값은 사업계획서와 같음" in st[1]["text"] and "사업계획서 기준으로 맞추기" not in st[1]["acts"], st[1])
        page.evaluate("(id) => openWork(id)", a)
        page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=a, timeout=120000)
        page.evaluate("() => showTab('Div')")
        page.wait_for_function(f"(id) => {{ const s = ({STEPS})()[1]; return state.id === id && !!s && s.text.includes('값은 사업계획서와 같음'); }}", arg=a, timeout=120000)
        page.evaluate("() => { window.planCalls = 0; divPlan = async () => { window.planCalls += 1; }; }")  # 계획은 따로 검사(지원 양식이 아니라 400) — 여기선 불렸는지만
        check("연차보고서 입력 값 = 사업계획서 값(당해 차년도도)", page.evaluate("() => [dv.values.stages, dv.values.orgs.lead, dv.values.orgs.joint, dv.values.current]") == [[2, 1], "가 기관", ["나 기관"], 2],
              page.evaluate("() => [dv.values.stages, dv.values.orgs.lead, dv.values.orgs.joint, dv.values.current]"))
        page.locator("#panel").screenshot(path=str(OUT / "6b_step2_shared.png"))
        st = page.evaluate(STEPS)
        check("① 값 같음 · 반영 전 → 「변경 계획 보기」", "값은 사업계획서와 같음" in st[1]["text"] and "반영 전" in st[1]["text"] and st[1]["acts"] == ["변경 계획 보기"], st[1])
        check("구성 확정 뒤 — 분석이 아직 없어 문서 검토가 현재 · 뒤 묶음은 대기(① 은 진행 가능 — 단계별로는 누를 수 있다)", [x[1] for x in page.evaluate(JOURNEY)] == ["done", "now", "todo", "todo", "todo"] and page.evaluate(CONFIG)["state"] == "done"
              and st[1]["state"] == "ready", (page.evaluate(JOURNEY), st[1]))
        page.evaluate("() => { window.journeyButton = document.querySelector('#taskFlow [data-journey=frame]'); window.journeyButton.focus(); taskStepsDraw(); }")
        check("순서 상태 갱신 — 이동 버튼과 키보드 초점 유지", page.evaluate("() => window.journeyButton.isConnected && document.activeElement === window.journeyButton"))
        # 2026-11-12 — 1단계 머리의 프레임 값 요약(기준 = 사업계획서 값) · 「구성 고치기」 · 입력하는 동안 단계 목록이 다시 그려져도 폼은 그대로(포커스 유지)
        fr = page.evaluate("() => { const f = document.querySelector('#taskStage .dv-phase-frame'); return { hidden: f.hidden, text: f.firstChild.textContent, title: f.firstChild.title, vis: f.checkVisibility() }; }")
        check("1단계 「구분 기준」 머리에 구성 요약 — 단계·차년도 · 주관 · 공동(접혀 있어도 보임)", not fr["hidden"] and fr["vis"] and fr["text"] == "1단계(1–2차년도) · 2단계(3차년도) · 주관 가 기관 · 공동 1(나 기관)"
              and "사업계획서" in fr["title"], fr)
        page.evaluate("() => { document.getElementById('taskStage').open = false; }")
        page.click("#taskStage [data-task-frame-edit]")
        page.wait_for_function("() => document.getElementById('taskStage').open && document.getElementById('taskFrameForm').contains(document.activeElement)")
        check("「구성 고치기」 — 1단계가 펴지고 과제 구성 입력으로 포커스", page.evaluate("() => document.getElementById('taskFrameForm').checkVisibility() && ['SELECT', 'INPUT'].includes(document.activeElement.tagName)"))
        page.evaluate("() => { const i = document.querySelector('#taskFrameForm .dv-org-field input'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); window.frameInput = i; window.frameOl = document.querySelector('#taskStage ol.dv-flow-steps'); }")
        page.keyboard.type("X")
        page.wait_for_function(f"() => ({CONFIG})().text.includes('확정한 뒤 값이 바뀌었습니다')")
        check("입력 중 — 단계 목록은 다시 그려지고(1단계 「구성 확정」 이 바로 「확정 뒤 바뀜」) 폼 노드·포커스는 그대로", page.evaluate("""() => document.activeElement === window.frameInput && window.frameInput.isConnected && window.frameInput.value === '가 기관X'
          && document.querySelector('#taskStage ol.dv-flow-steps') !== window.frameOl && dv.values.orgs.lead === '가 기관X' && document.getElementById('divReviewSummary').isConnected"""),
              page.evaluate("() => [document.activeElement && document.activeElement.tagName, window.frameInput.isConnected, window.frameInput.value, dv.values.orgs.lead]"))
        page.keyboard.press("Backspace")
        page.wait_for_function(f"() => ({STEPS})()[1].text.includes('값은 사업계획서와 같음')")
        check("되돌리면 1단계 확정·① 도 되돌아감 · 포커스 그대로", page.evaluate("() => document.activeElement === window.frameInput && dv.values.orgs.lead === '가 기관'"))
        for width in (320, 480):  # 펼친 1단계(과제 구성 입력 포함) — 패널 최소 폭·보통 폭에서 가로 넘침 없음(design.md §1-8)
            page.evaluate("(w) => document.getElementById('panel').style.setProperty('--panel', w + 'px')", width)
            page.wait_for_timeout(300)
            check(f"펼친 1단계 과제 구성 입력 가로 넘침 없음(패널 {width}px)", page.evaluate("""() => { const t = document.querySelector('#divBox .dv-task'), r = t.getBoundingClientRect(), f = document.getElementById('taskFrameForm'), a = document.getElementById('taskFrameApply');
              return t.scrollWidth <= t.clientWidth + 1 && f.scrollWidth <= f.clientWidth + 1 && a.scrollWidth <= a.clientWidth + 1 && [...f.querySelectorAll('input, select, button, .dv-card'), ...a.querySelectorAll('.dv-applied, .dv-run, button'), ...t.querySelectorAll('#taskStage0 summary > *, #taskStage summary > *')]
                .filter((e) => e.checkVisibility()).every((e) => { const b = e.getBoundingClientRect(); return b.left >= r.left - 1 && b.right <= r.right + 1; }); }"""))
            page.locator("#panel").screenshot(path=str(OUT / f"6b2_frame_form_{width}.png"))
        page.evaluate("() => { document.getElementById('panel').style.removeProperty('--panel'); document.getElementById('taskStage').open = false; }")
        st = page.evaluate(STEPS)
        page.evaluate("() => { dv.values.stages = [2, 2]; divTouched(); divRender(); }")
        st = page.evaluate(STEPS)
        check("입력 값(프로젝트 구성)을 바꾸면 바로 1단계가 「확정 뒤 바뀜」 · ① 은 대기", "확정한 뒤 값이 바뀌었습니다" in page.evaluate(CONFIG)["text"] and st[1]["state"] == "todo" and not st[1]["acts"], (page.evaluate(CONFIG), st[1]))
        page.evaluate("() => { dv.values.stages = [2, 1]; dv.values.current = 3; divTouched(); divRender(); }")  # 다른 해의 보고서 — 사람이 연차보고서 입력에서 바꾼 것
        FAKE_APPLIED = "() => { dv.view.applied = { values: JSON.parse(divCanon(dv.values)), rev: state.serverRev, at: Date.now() / 1000 }; taskStepsDraw(); }"  # 반영은 지원 양식에서만 — 반영 기록을 화면에 얹어 본다
        page.evaluate(FAKE_APPLIED)
        st = page.evaluate(STEPS)
        check("구조 반영 뒤에도 분석이 없으면 문서 검토가 현재(당해 차년도만 바꾼 것은 확정을 안 풂 — ① 은 끝남)", page.evaluate(JOURNEY) == [["prepare", "done", None], ["review", "now", "step"], ["frame", "todo", None], ["map", "todo", None], ["clean", "todo", None]]
              and page.evaluate(CONFIG)["state"] == "done" and st[1]["state"] == "done", page.evaluate(JOURNEY))
        check("① 반영됨(당해 차년도는 안 견줌 — 다르면 글로 보임) → 분석이 없어 ② 는 대기 · 1단계 「헤딩 · 표 분석」 이 지금(「분석」) · 다시 분석 줄도 대기", [s["state"] for s in st][:6] == ["done", "done", "todo", "todo", "todo", "soon"] and "연차보고서에 반영됨" in st[1]["text"]
              and "당해 차년도는 연차보고서 3차년도(사업계획서 2차년도)" in st[1]["text"]
              and not st[2]["acts"] and page.evaluate(STEP, "heads")["state"] == "now" and page.evaluate(STEP, "heads")["acts"] == ["분석"] and page.evaluate(STEP, "reheads")["state"] == "todo", (st, page.evaluate(STEP, "heads"), page.evaluate(STEP, "reheads")))
        page.locator("#panel").screenshot(path=str(OUT / "6c_step3.png"))
        for width in (320, 480):  # 패널 최소 폭·보통 폭에서 가로 넘침 없음(design.md §1-8)
            page.evaluate("(w) => document.getElementById('panel').style.setProperty('--panel', w + 'px')", width)
            page.wait_for_timeout(300)
            check(f"첫 카드 가로 넘침 없음(패널 {width}px)", page.evaluate("() => { const t = document.querySelector('#divBox .dv-task'); return t.scrollWidth <= t.clientWidth + 1 && [...t.querySelectorAll('select, button')].every((e) => e.getBoundingClientRect().right <= t.getBoundingClientRect().right + 1); }"))
            page.locator("#panel").screenshot(path=str(OUT / f"6d_panel_{width}.png"))
        page.evaluate("() => document.getElementById('panel').style.removeProperty('--panel')")
        check("② 줄에 「문서 비교에서 추출」 단추 없음 — 분석은 1단계의 몫(§21)", page.locator("#taskSteps button", has_text="문서 비교에서 추출").count() == 0)

        # ---- 7. 문서 비교 — 같은 과제 문서를 처음부터 함께 고름 · 분석 없는 것을 함께 추출(스크립트만) · 목록에 과제·첨부 파일 종류
        page.click("#tabCompare")
        page.wait_for_selector("#paneCompare .mc-work-option")
        row = page.locator("#paneCompare .mc-work-option", has_text=f"작업 {a}").inner_text()
        check("비교 목록에 프로젝트·라운드·첨부 파일 종류(② §17)", "프로젝트 시험 과제 · Round 1" in row and "연차보고서" in row, row)
        check("같은 과제 문서 둘이 처음부터 고름", page.evaluate("() => [...mergeCompare.selected].sort()") == sorted([a, c]))
        page.locator("#paneCompare .mc-actions button", has_text="선택 문서 비교").click()
        page.wait_for_function("() => !mergeCompare.busy && mergeCompare.snapshots.length === 2", timeout=30000)
        btn = page.locator("#paneCompare .mc-actions button", has_text="분석 없는 문서 2개 추출")
        check("「분석 없는 문서 2개 추출」 단추", btn.count() == 1)
        t0 = time.time()
        btn.click()
        page.wait_for_function("""() => !mergeCompare.busy && mergeCompare.snapshots.length === 2
            && mergeCompare.snapshots.every((s) => mcReadiness(s, 'stage2') === 'ready' && mcReadiness(s, 'stage3') === 'ready')""", timeout=180000)
        check("두 문서 모두 헤딩 그래프·표 구조 생김", page.evaluate("() => mergeCompare.error") == "", f"{time.time() - t0:.1f}s")
        check("추출 단추 사라짐", page.locator("#paneCompare .mc-actions button", has_text="추출").count() == 0)
        page.screenshot(path=str(OUT / "7_compare.png"))
        # ---- 8. ② 자리 연결(spec_작업 ② §11 · API …/merge-links) — 추출 뒤 「연구개발과제」 내용으로 돌아오면(패널 머리 탭 「작업 개요」) 앞 조건(헤딩·표 분석)이 채워지고 서버에 연결 목록을 묻는다
        page.click("#toolTabTask")
        page.wait_for_function("(ids) => ids.every((i) => taskFlow.heads[i] && taskFlow.heads[i].stage2 && taskFlow.heads[i].stage3) && taskFlow.links && !taskFlow.linkBusy", arg=[a, c], timeout=30000)
        page.evaluate(FAKE_APPLIED)
        st = page.evaluate(STEPS)
        check("② 실제 서버 답 — 낼 수 없는 까닭을 문서별로(연차보고서: 구분 기준 반영 전) · 「다시 읽기」", [s["state"] for s in st][:6] == ["done", "done", "now", "todo", "todo", "soon"]
              and "연결 목록을 낼 수 없습니다" in st[2]["text"] and "연차보고서: 프로젝트 구성 반영 전" in st[2]["text"] and "사업계획서:" not in st[2]["text"] and st[2]["acts"] == ["다시 읽기"], st[2])
        # ---- 8-0. LLM 검증·보완 줄(spec_작업 ② §21 — 2026-11-19 사용자 "1단계 문서 검토에서 LLM 도 들어 가야지"). 이 서버는 LLM 이 꺼져 있어 지금까지 두 LLM 줄은 「건너뜀」 이었다 —
        # LLM 을 쓸 수 있는 것으로 바꿔(화면 값) 줄의 상태 · 「건너뛰기」 · 「LLM 검증·보완」(끝점은 흉내: POST …/analysis/llm 202 · 그 문서의 헤딩 요약에 LLM 을 거친 표시)을 본다
        hl0, rl0 = page.evaluate(STEP, "headsLlm"), page.evaluate(STEP, "reheadsLlm")
        check("LLM 을 쓸 수 없는 서버 — 두 LLM 줄(1단계 「LLM 검증·보완」 · 2단계 「다시 문서 검토(LLM)」)은 건너뜀으로 끝남 · 단추 없음", hl0["state"] == "done" and "LLM 을 쓸 수 없어 건너뜁니다" in hl0["text"] and not hl0["acts"]
              and rl0["state"] == "done" and "건너뜀" in rl0["text"] and not rl0["acts"] and "다시 문서 검토(LLM)" in rl0["text"], (hl0, rl0))
        page.evaluate("() => { taskLlmOk = true; taskStepsDraw(); }")
        hl, st = page.evaluate(STEP, "headsLlm"), page.evaluate(STEPS)
        check("LLM 을 쓸 수 있으면 — 1단계 「LLM 검증·보완」 이 지금(원본 문서 = 사업계획서 · 유료) · 「LLM 검증·보완」(강조) · 「건너뛰기」 · ② 는 대기(이관 조건: 1 · 2단계가 먼저)",
              hl["state"] == "now" and hl["acts"] == ["LLM 검증·보완", "건너뛰기"] and "사업계획서의 헤딩 · 템플릿" in hl["text"] and "유료" in hl["text"] and st[2]["state"] == "todo"
              and page.evaluate("() => document.querySelector('#taskSteps li[data-step=headsLlm] button').classList.contains('primary')")
              and page.evaluate(STEP, "reheadsLlm")["state"] == "todo" and [x[1] for x in page.evaluate(JOURNEY)] == ["done", "now", "todo", "todo", "todo"], (hl, st[2], page.evaluate(JOURNEY)))
        page.locator("#taskSteps li[data-step=headsLlm] button", has_text="건너뛰기").click()
        hl, rl = page.evaluate(STEP, "headsLlm"), page.evaluate(STEP, "reheadsLlm")
        check("「건너뛰기」 — 그 문서는 스크립트 분석만으로(건너뜀 · 「건너뛰기 취소」 · 이 브라우저에 기억) → 다음은 2단계의 「다시 문서 검토(LLM)」(목적 문서 = 연차보고서)",
              hl["state"] == "done" and "건너뜀 — 사업계획서는 스크립트 분석만으로" in hl["text"] and hl["acts"] == ["건너뛰기 취소"] and page.evaluate("(id) => JSON.parse(localStorage.getItem('nfm.relayLlmSkip')).includes(id)", c)
              and rl["state"] == "now" and rl["acts"] == ["LLM 검증·보완", "건너뛰기"] and "연차보고서의 헤딩 · 템플릿" in rl["text"], (hl, rl))
        llm_calls = []

        def analysis_route(route):  # 「LLM 검증·보완」 의 끝점 흉내 — 걸면 202(도는 작업), 그 뒤 그 문서의 헤딩 요약은 「LLM 을 거침 · 끝남」
            req = route.request
            if req.method == "POST" and req.url.endswith("/analysis/llm"):
                llm_calls.append(req.url.split("/api/docs/")[1].split("/")[0])
                return route.fulfill(status=202, content_type="application/json", body=json.dumps({"stage": 2, "llm": True, "chain": "llm", "status": "running", "error": None, "started": time.time(), "steps": []}))
            if req.method == "GET" and req.url.endswith("/headings") and llm_calls and f"/api/docs/{llm_calls[-1]}/" in req.url:
                got = requests.get(req.url, timeout=60).json()
                for k in ("stage2", "stage3"):
                    got[k]["llm"] = {**(got[k].get("llm") or {}), "requested": True, "fallback": False}
                got["job"] = None
                return route.fulfill(status=200, content_type="application/json", body=json.dumps(got, ensure_ascii=False))
            return route.continue_()
        page.route(re.compile(r"/api/docs/[^/]+/(analysis/llm|headings)$"), analysis_route)
        was_open = page.evaluate("() => { const b = document.getElementById('taskStage'), was = b.open; b.open = true; return was; }")   # 2단계 묶음은 위에서 접어 뒀다 — 줄의 단추를 누르려면 편다
        page.locator("#taskSteps li[data-step=reheadsLlm] button", has_text="LLM 검증·보완").click()
        page.wait_for_function(f"() => {{ const s = ({STEP})('reheadsLlm'); return !!s && s.state === 'done' && s.text.includes('LLM 검증·보완을 거쳤습니다'); }}", timeout=60000)
        rl, st = page.evaluate(STEP, "reheadsLlm"), page.evaluate(STEPS)
        check("「LLM 검증·보완」 — 그 문서(연차보고서)로 한 번 걸고(POST …/analysis/llm) 끝나면 줄이 「LLM 검증·보완을 거쳤습니다」 · 단추 없음 → 1 · 2단계가 끝나 ② 가 지금",
              llm_calls == [a] and rl["state"] == "done" and not rl["acts"] and st[2]["state"] == "now", (llm_calls, rl, st[2]))
        page.unroute(re.compile(r"/api/docs/[^/]+/(analysis/llm|headings)$"))
        page.evaluate("(open) => { document.getElementById('taskStage').open = open; }", was_open)
        page.locator("#taskSteps li[data-step=headsLlm] button", has_text="건너뛰기 취소").click()
        check("「건너뛰기 취소」 — 다시 1단계의 할 일(지금) · 기억에서 빠짐", page.evaluate(STEP, "headsLlm")["state"] == "now" and page.evaluate("() => localStorage.getItem('nfm.relayLlmSkip')") == "[]", page.evaluate(STEP, "headsLlm"))
        # 묶음의 「한 번에 진행」 도 LLM 단계를 한다(taskRunLlm — 걸고 끝날 때까지 읽음): 1단계에 「LLM 검증·보완」(사업계획서)이 남았다 → 누르면 그 문서로 한 번 걸고 끝 글에 적는다
        llm_calls.clear()
        page.route(re.compile(r"/api/docs/[^/]+/(analysis/llm|headings)$"), analysis_route)
        page.evaluate("() => { taskRunLast = null; document.getElementById('taskStageR').open = false; }")
        r1 = page.evaluate("() => { const b = document.querySelector('#taskStageR [data-task-run]'); return { disabled: b.disabled, state: document.querySelector('#taskStageR .dv-phase-state').textContent }; }")
        page.click("#taskStageR [data-task-run]")
        page.wait_for_function("() => !taskRun && !!taskRunLast", timeout=120000)
        last = page.evaluate("() => taskRunLast")
        check("1단계 「한 번에 진행」 — 남은 일이 LLM 검증·보완뿐: 사업계획서로 한 번 걸고(문서는 안 바뀜) 끝 글 「… 사업계획서 LLM 검증·보완을 거쳤습니다」 · 그 줄이 끝남", not r1["disabled"] and r1["state"].startswith("다음: LLM 검증·보완")
              and last["ok"] and last["stage"] == "review" and "사업계획서 LLM 검증·보완을 거쳤습니다" in last["text"] and llm_calls == [c]
              and page.evaluate(STEP, "headsLlm")["state"] == "done" and "LLM 검증·보완을 거쳤습니다" in page.evaluate(STEP, "headsLlm")["text"], (r1, last, llm_calls))
        page.unroute(re.compile(r"/api/docs/[^/]+/(analysis/llm|headings)$"))
        page.evaluate("() => { taskRunLast = null; taskRunEnds = {}; document.getElementById('taskStageR').open = true; }")
        page.evaluate("() => { taskLlmOk = false; return taskFlowLoad(); }")   # 뒤 검사는 LLM 이 꺼진 서버 그대로(두 LLM 줄은 건너뜀)
        page.evaluate(FAKE_APPLIED)   # 「한 번에 진행」 이 프로젝트 구성을 다시 읽었다 — 화면에 얹은 반영 기록을 다시
        page.wait_for_function(f"() => !taskFlow.linkBusy && !!taskFlow.links && ({STEP})('reheadsLlm').state === 'done' && ({STEP})('headsLlm').state === 'done'", timeout=60000)
        # 연결 목록이 나온 화면은 가짜 응답으로(반영은 지원 양식에서만) — 묶음 넷(연결됨 · 확인 필요 · 후보 없음 · 원본에만), PUT 은 고른 대로 바꿔 돌려준다. 응답 꼴은 app/merge_api.py
        pid = page.evaluate("() => document.querySelector('#doc .para[data-id]').dataset.id")
        cand = [{"key": "p900", "path": ["연구개발비 사용에 관한 계획", "연구개발기관별 사용계획"], "label": "주관연구개발기관 : ]", "score": 0.664},
                {"key": "p901", "path": ["연구개발기관 현황"], "label": "주관연구개발기관책임자", "score": 0.287}]

        def item(value, linked=True):
            return {"value": value, "to": {"id": pid, "text": f"[{value} 자리]"}, "from": {"id": "p900", "text": f"[{value} 원본]", "value": value} if linked else None, "status": "paired" if linked else "unpaired"}
        base = {"dim": "org", "dimName": "기관", "kind": "paragraph", "source": "script", "reason": "", "anchor": None, "ctx": {"year": 1, "org": None}}
        groups0 = [
            {**base, "id": "g1", "status": "paired", "to": {"key": "g1", "path": ["다음 연도 연구개발계획", "연구개발기관별 사용계획 총괄표"], "label": "주관연구개발기관 : ]"}, "from": cand[0], "candidates": cand, "items": [item("주관"), item("공동1")]},
            {**base, "id": "g2", "status": "ambiguous", "reason": "후보가 여럿이거나 닮음이 낮음", "to": {"key": "g2", "path": ["해당연도 추진 실적 및 추진내용"], "label": "주관연구개발기관명 : ]"}, "from": None, "candidates": cand, "items": [item("주관", False)]},
            {**base, "id": "g3", "dim": "year", "dimName": "차년도", "kind": "cols", "status": "toOnly", "to": {"key": "g3", "path": ["정량적 연구개발성과"], "label": "", "table": "t9"}, "from": None, "candidates": [], "items": [item("1차년도", False)]},
            {**base, "id": "from:p950", "status": "fromOnly", "to": None, "from": {"key": "p950", "path": ["연구개발 목표 및 내용", "개발 목표"], "label": "주관연구개발기관()]"}, "candidates": [], "items": []}]
        links = {"groups": copy.deepcopy(groups0), "calls": []}

        PLAN = {"planId": "pl1", "baseRev": 0, "todo": 5,
                "body": {"counts": {"todo": 1, "noSource": 1}, "items": [
                    {"group": "g1", "value": "주관", "to": pid, "from": "p900", "anchorText": "- (추진 내용)", "blocks": 3, "paragraphs": 2, "tables": 1, "pictures": 0, "skip": None, "detail": ""},
                    {"group": "g1", "value": "공동1", "to": pid, "from": None, "anchorText": "- (추진 내용)", "blocks": 0, "paragraphs": 0, "tables": 0, "pictures": 0, "skip": "noSource", "detail": "원본 항목 없음"}]},
                "tables": {"counts": {"cells": 3, "calc": 1, "rows": 1, "skipped": {"occupied": 1, "noSource": 0}},
                           "tables": [{"group": "g3", "kind": "cols", "mode": "fixed", "to": "t9", "from": "t1", "cells": 3, "rows": 1, "skipped": 1}], "skipped": []}}

        def links_route(route):
            req = route.request
            body = req.post_data_json if req.method != "GET" and req.post_data else None
            tail = unquote(req.url.split("/merge-links", 1)[1])
            links["calls"].append((req.method, tail, body))
            if tail == "/plan":
                return route.fulfill(status=200, content_type="application/json", body=json.dumps(PLAN))
            if tail == "/apply":
                return route.fulfill(status=200, content_type="application/json", body=json.dumps({
                    "body": {"items": 1, "blocks": 3}, "tables": {"filled": 3, "rowsAdded": 1}, "converted": {"converted": 0}, "dropped": [],
                    "rev": links["rev"], "editedCount": 0, "unrestored": [], "pristine": None, "kinds": {}, "undo": 1, "owpml": None, "persistError": None}))
            if tail == "/llm":   # LLM 검토 — 확인 필요한 g2 를 잇는다(source llm)
                i = next(k for k, g in enumerate(links["groups"]) if g["id"] == "g2")
                links["groups"][i] = {**links["groups"][i], "status": "paired", "from": cand[1], "source": "llm", "reason": "소속과 안쪽 소제목이 같은 뜻"}
                links["llm"] = {"at": "2026-11-11T18:00:00", "units": [{"title": "2.", "pages": [5, 10], "over": False, "targets": 2, "call": {"model": "claude-opus-5-5"}}], "none": [], "rejected": 0, "left": 0}
            elif req.method == "PUT":
                i = next(k for k, g in enumerate(links["groups"]) if g["id"] == unquote(req.url.rsplit("/", 1)[1]))
                if body.get("reset"):
                    links["groups"][i] = copy.deepcopy(groups0[i])
                else:
                    f = next((x for x in cand if x["key"] == body["from"]), None)
                    links["groups"][i] = {**links["groups"][i], "status": "paired" if f else "toOnly", "from": f, "source": "user"}
            counts = {k: sum(g["status"] == k for g in links["groups"]) for k in ("paired", "ambiguous", "toOnly", "fromOnly")}
            route.fulfill(status=200, content_type="application/json", body=json.dumps({
                "project": "시험 과제", "from": {"work": c, "name": "사업계획서.hwpx", "rev": 0, "reasons": []}, "to": {"work": a, "name": "연차보고서.hwpx", "rev": 0, "reasons": []},
                "diff": [], "stale": False, "groups": links["groups"], "counts": counts, "llm": links.get("llm"),
                "fixed": {"counts": {"tables": 2, "tablesLlm": 1, "cells": 0, "labels": 0}, "todo": 0}}))   # 같은 이름 자리 0 · 같은 표 2(LLM 1) — ② 줄 글(2026-11-12)
        LINKS_URL = re.compile(r"/api/docs/[^/]+/merge-links")
        page.route(LINKS_URL, links_route)
        LINKS_DONE = "() => taskFlow.links && taskFlow.links.groups && !taskFlow.linkBusy"
        ROWS = "() => [...document.querySelectorAll('#headsDlgBody tr[data-link]')].map((tr) => ({ id: tr.dataset.link, status: tr.dataset.status, text: tr.textContent, sel: (tr.querySelector('select') || {}).value }))"
        # 이 절은 LLM 검토 화면을 흉내 낸다 — 검사 서버의 LLM 은 꺼져 있어도 쓸 수 있는 것으로(못 쓰면 「자리 연결」 은 「건너뜀」 — 바로 아래) · 두 문서의 LLM 검증·보완 줄은 「건너뛰기」 로 끝난 채(앞 절과 같은 차례)
        page.evaluate("() => { taskLlmOk = true; taskLlmAsked = true; taskLlmSkip(taskSlotDoc('plan'), true); taskLlmSkip(taskSlotDoc('report'), true); }")
        page.evaluate("() => taskFlowLoad()")
        page.wait_for_function("() => taskFlow.links && taskFlow.links.groups && taskFlow.links.groups.length === 4 && !taskFlow.linkBusy")
        page.evaluate(FAKE_APPLIED)
        page.evaluate("() => { taskLlmOk = false; taskStepsDraw(); }")
        off = page.evaluate(STEPS)[2]
        check("② LLM 을 쓸 수 없으면 「자리 연결」 은 「건너뜀」 으로 끝 — 확인 필요는 비워 둔다(서버 실행기의 상태 식과 같다 · 막다른 길 없음)", off["state"] == "done" and off["badge"] == "건너뜀" and "LLM 을 쓸 수 없어 확인 필요 1곳은 넣지 않고 비워 둡니다" in off["text"], off)
        page.evaluate("() => { taskLlmOk = true; taskStepsDraw(); }")
        st = page.evaluate(STEPS)
        PRIMARY = "(step) => [...document.querySelectorAll(`#taskSteps li[data-step=${step}] button`)].map((b) => b.classList.contains('primary'))"  # 그 단계 단추들의 강조 여부
        check("② 연결 목록이 나옴 — 다음 작업은 LLM 검토 · ③은 먼저 진행 가능", [s["state"] for s in st][:6] == ["done", "done", "now", "ready", "todo", "soon"]
              and st[2]["badge"] == "다음 작업" and st[3]["badge"] == "진행 가능"
              and "연결됨 1 · 확인 필요 1 · 후보 없음 1 · 원본에만 1" in st[2]["text"] and "다음: 「LLM 검토」" in st[2]["text"] and st[2]["acts"] == ["LLM 검토", "연결 목록", "지침", "매칭 지침"]   # 「매칭 지침」 — spec_병합 ② §5-6(2026-11-22 — 전의 「연결 코멘트」 단추: ② §5-3 1 · 2026-11-12)
              and page.evaluate(PRIMARY, "link") == [True, False, False, False] and st[3]["acts"] == ["넣기 계획"] and page.evaluate(PRIMARY, "plan") == [False], [st[2:4], page.evaluate(PRIMARY, "link")])
        page.locator("#taskSteps button", has_text="연결 목록").click()
        page.wait_for_selector("#headsDlg[data-kind=links] #headsDlgBody tr[data-link]")
        rows = page.evaluate(ROWS)
        check("연결 목록은 문서 옆 열(팝업 아님) · 처음에는 확인 필요만", page.evaluate(VIS, "headsDlg") and page.locator("dialog[open]").count() == 0 and [r["id"] for r in rows] == ["g2"]
              and "자리 연결 — 연결 목록" in page.inner_text("#headsDlgTitle") and "사업계획서.hwpx → 연차보고서.hwpx" in page.inner_text("#headsDlgNote"), rows)
        page.locator("#headsDlgTools button", has_text="모두 4").click()
        rows = page.evaluate(ROWS)
        check("「모두」 — 묶음 넷, 상태 글 · 자리(연차보고서 ← 사업계획서)", [(r["id"], r["status"]) for r in rows] == [("g1", "paired"), ("g2", "ambiguous"), ("g3", "toOnly"), ("from:p950", "fromOnly")]
              and "연결됨" in rows[0]["text"] and "확인 필요" in rows[1]["text"] and "후보 없음" in rows[2]["text"] and "원본에만" in rows[3]["text"]
              and "기관 · 본문" in rows[0]["text"] and "차년도 · 표 열" in rows[2]["text"] and "연구개발기관별 사용계획 총괄표" in rows[0]["text"] and rows[0]["sel"] == "p900" and rows[1]["sel"] == ""
              and "2/2" in rows[0]["text"] and "0/1" in rows[1]["text"], rows)
        page.screenshot(path=str(OUT / "8a_links.png"))
        page.select_option("#headsDlgBody tr[data-link=g2] select", "p901")
        try:
            page.wait_for_function(f"() => ({LINKS_DONE})() && taskFlow.links.counts.ambiguous === 0")
        except Exception:
            print("DEBUG calls", links["calls"], "errors", errors, "toast", page.inner_text("#toast"), "links", page.evaluate("() => JSON.stringify([taskFlow.linkBusy, taskFlow.links && taskFlow.links.counts])"), flush=True)
            raise
        rows, st = page.evaluate(ROWS), page.evaluate(STEPS)
        check("확인 필요한 자리의 원본을 고름 — PUT {from} · 「고름」 표시 · ② 끝남(단추는 남음) · ③ 넣기 계획이 지금", links["calls"][-1] == ("PUT", "/g2", {"from": "p901"})
              and rows[1]["status"] == "paired" and "고름" in rows[1]["text"] and "되돌리기" in rows[1]["text"] and rows[1]["sel"] == "p901"
              and [s["state"] for s in st][:6] == ["done", "done", "done", "now", "todo", "soon"] and "연결됨 2 · 확인 필요 0" in st[2]["text"] and st[2]["acts"] == ["연결 목록", "LLM 검토", "지침", "매칭 지침"] and st[3]["acts"] == ["넣기 계획"]
              and page.evaluate(PRIMARY, "link") == [False, False, False, False] and page.evaluate(PRIMARY, "plan") == [True], [links["calls"][-1], rows[1], st[2:]])  # 확인 필요가 없으면 강조는 ③ 넣기 계획(카드에 하나)
        page.select_option("#headsDlgBody tr[data-link=g1] select", "")
        page.wait_for_function(f"() => ({LINKS_DONE})() && taskFlow.links.counts.toOnly === 2")
        check("「연결 안 함」 — PUT {from: null}", links["calls"][-1] == ("PUT", "/g1", {"from": None}) and page.evaluate(ROWS)[0]["status"] == "toOnly", links["calls"][-1])
        for gid in ("g1", "g2"):
            page.locator(f"#headsDlgBody tr[data-link={gid}] button", has_text="되돌리기").click()
            page.wait_for_function("(gid) => !taskFlow.linkBusy && taskFlow.links.groups.find((g) => g.id === gid).source === 'script'", arg=gid)
        rows = page.evaluate(ROWS)
        check("「되돌리기」 — PUT {reset: true} · 스크립트 결과로", links["calls"][-1] == ("PUT", "/g2", {"reset": True}) and [r["status"] for r in rows] == ["paired", "ambiguous", "toOnly", "fromOnly"]
              and "고름" not in rows[0]["text"] + rows[1]["text"], [links["calls"][-2:], rows[:2]])
        page.locator("#headsDlgBody tr[data-link=g1] td.lk-place .lk-to").click()
        page.wait_for_selector("#headsDlgBody tr.lk-items li")
        items = page.eval_on_selector_all("#headsDlgBody tr.lk-items li", "ls => ls.map(l => l.textContent)")
        check("줄을 누르면 항목이 펴짐(구분 값마다 연차보고서 글 ← 사업계획서 글)", items == ["주관 [주관 자리] ← [주관 원본]", "공동1 [공동1 자리] ← [공동1 원본]"], items)
        page.locator("#headsDlgBody tr.lk-items li").first.click()
        n = len(links["calls"])
        page.locator("#headsDlgFoot button", has_text="다시 내기").click()
        page.wait_for_function(f"(n) => ({LINKS_DONE})()", arg=n)
        check("「다시 내기」 — POST", links["calls"][-1][0] == "POST" and "연결됨 1 · 확인 필요 1" in page.inner_text("#headsDlgFoot"), links["calls"][-1])
        check("연결 목록 가로 넘침 없음", page.evaluate("() => { const b = document.getElementById('headsDlgBody'); return b.scrollWidth <= b.clientWidth + 1; }"))
        page.screenshot(path=str(OUT / "8b_links_open.png"))
        page.locator("#headsDlgFoot button", has_text="닫기").click()
        check("닫기 — 열이 닫히고 ② 줄은 그대로", page.eval_on_selector("#headsDlg", "e => e.hidden") and page.evaluate(STEPS)[2]["acts"] == ["LLM 검토", "연결 목록", "지침", "매칭 지침"])
        # ---- 매칭 지침(2열 kind linkGuides — spec_병합 ② §5-6: 2026-11-22 사용자 "테이블, 본문별로 어떻게 매칭해야하는지 지침을 관리하고" · 전의 「연결 코멘트」 단추는 정의되지 않은 함수를 불렀다). 끝점은 진짜(GET …/link-guides — 문서는 안 바뀐다)
        page.locator("#taskSteps li[data-step=link] button", has_text="매칭 지침").click()
        page.wait_for_function("() => heads.dlg === 'linkGuides' && !document.getElementById('headsDlg').hidden")
        check("「매칭 지침」 — 문서 옆 열(팝업 아님)에 「매칭 지침 — 표/본문별」 · LLM 검토가 읽는 글이고 스크립트는 안 바뀐다는 안내", page.inner_text("#headsDlgTitle") == "매칭 지침 — 표/본문별"
              and "스크립트가 넣는 방식은 이 글로 바뀌지 않습니다" in page.inner_text("#headsDlgBody") and page.evaluate("() => !document.querySelector('dialog[open]')"), page.inner_text("#headsDlgTitle"))
        page.locator("#headsDlgFoot button", has_text="닫기").click()
        check("매칭 지침 닫기 — 열이 닫힘", page.eval_on_selector("#headsDlg", "e => e.hidden"))
        # ---- 9. LLM 검토 · ③ 넣기 계획 · ④ 내용 반영(spec_병합 ② §0-1 · §4 · §6 — API …/merge-links/llm · /plan · /apply, 가짜 응답)
        page.locator("#taskSteps li[data-step=link] button", has_text="LLM 검토").click()   # ② 줄의 것 — 1단계 묶음 안의 「구분 기준 자리 표시」 에도 「LLM 검토」 가 있다
        page.wait_for_function("() => taskFlow.links && taskFlow.links.llm && !taskFlow.llmBusy && !taskFlow.linkBusy")
        st = page.evaluate(STEPS)
        check("「LLM 검토」 — POST …/llm · ② 줄에 「LLM 검토함(1단위)」 · 확인 필요 0", ("POST", "/llm", {}) in links["calls"] and "LLM 검토함(1단위)" in st[2]["text"] and "확인 필요 0" in st[2]["text"]
              and st[2]["acts"] == ["연결 목록", "LLM 다시 검토", "지침", "매칭 지침"], st[2])
        check("② 줄 수 글 — 「같은 이름 자리 N」 뒤에 「같은 표 T(LLM t)」", "같은 이름 자리 0 · 같은 표 2(LLM 1)" in st[2]["text"], st[2]["text"])
        # ---- LLM 지침·프롬프트 보기(2열 kind llmGuide — 2026-11-12 사용자 "각 LLM이 검토나 작업할때 '지침' 이나 프롬프트를 확인할 수 있으면"). 끝점은 흉내(정규식 route — 글롭은 하위 경로를 안 잡는다)
        GUIDE = {"step": "merge-links", "name": "자리 연결 LLM 검토", "model": "claude-opus-5-5", "parts": [
            {"key": "contract", "title": "계약(역할·자료·답의 꼴)", "text": "당신은 … 검토자입니다.", "source": "", "note": ""},
            {"key": "guide", "title": "판단 지침", "text": "- 같은 표는 같게 잇는다\n- 특정 기관·차년도의 표는 가려서 잇는다 " + "긴글" * 200, "source": "app/merge_guides_default/links.md", "note": "자리 연결 LLM 검토의 판단 기준"},
            {"key": "job", "title": "할 일 프롬프트 — 사업계획서 → 연차보고서 이관", "text": "## 이 일은\n- 연구개발계획서에서 연차보고서에 필요한 내용을 추출", "source": "jobs/plan_to_report.md", "note": ""},
            {"key": "form", "title": "양식 정보 — 연차보고서", "text": "양식 글", "source": "", "note": ""}],
            "last": {"at": "2026-11-12T07:00:00", "units": [{"n": 1, "title": "첫 장 앞(표지·요약문·목차)", "pages": [1, 5], "targets": 1, "chars": 12345, "error": None, "has": True},
                                                          {"n": 2, "title": "1. 연구개발과제의 개요", "pages": [5, 5], "targets": 0, "chars": 0, "error": None, "has": False}]}}
        guide_calls = []

        def guide_route(route):
            url = route.request.url
            guide_calls.append(unquote(url.split("/api/docs/", 1)[1]))
            if "/prompt" in url:
                return route.fulfill(status=200, content_type="application/json", body=json.dumps({"at": GUIDE["last"]["at"], "title": "첫 장 앞", "prompt": "계약 글\n\n## 자료(JSON)\n{\"targets\":[]}",
                                                                                                    "answer": {"decisions": [], "summary": "없음"}}, ensure_ascii=False))
            if "/division-missing" in url:   # 끝점이 아직 없는 서버(재시작 전) — FastAPI 의 404
                return route.fulfill(status=404, content_type="application/json", body=json.dumps({"detail": "Not Found"}))
            div = "/division-review" in url
            route.fulfill(status=200, content_type="application/json", body=json.dumps({**GUIDE, "step": "division-review" if div else "merge-links", "name": "구분 기준 LLM 재검토" if div else GUIDE["name"],
                                                                                        "model": None if div else GUIDE["model"], "last": None if div else GUIDE["last"]}, ensure_ascii=False))
        GUIDE_URL = re.compile(r"/api/docs/[^/]+/llm-guide/")
        page.route(GUIDE_URL, guide_route)
        page.click("#taskSteps li[data-step=link] button[data-llm-guide=merge-links]")
        page.wait_for_function("() => document.querySelectorAll('#headsDlg[data-kind=llmGuide] #headsDlgBody details.lg-part').length === 4")
        g = page.evaluate("""() => { const b = document.getElementById('headsDlgBody'), ds = [...b.querySelectorAll('details.lg-part')];
          return { title: document.getElementById('headsDlgTitle').textContent, tools: document.getElementById('headsDlgTools').textContent, open: ds.map((d) => d.open), keys: ds.map((d) => d.dataset.part),
            src: ds.map((d) => d.querySelector('.lg-src').textContent), note: ds.map((d) => (d.querySelector('.lg-note') || {}).textContent || ''), guide: ds[1].querySelector('pre.lg-text').textContent,
            ws: getComputedStyle(ds[1].querySelector('pre.lg-text')).whiteSpace, over: b.scrollWidth - b.clientWidth, body: b.textContent,
            units: [...b.querySelectorAll('.lg-unit-head')].map((h) => ({ text: h.textContent, disabled: h.disabled })) }; }""")
        check("「지침」 — 문서 옆 열(팝업 아님)에 「LLM 지침 — 자리 연결 LLM 검토」 · 모델", page.evaluate(VIS, "headsDlg") and page.locator("dialog[open]").count() == 0 and g["title"] == "LLM 지침 — 자리 연결 LLM 검토"
              and "claude-opus-5-5" in g["tools"] and f"{a}/llm-guide/merge-links" in guide_calls, [g["title"], g["tools"], guide_calls])
        check("함께 보내는 글 넷 — 판단 지침·할 일 프롬프트는 펴고 계약·양식 정보는 접음 · 파일 경로 · 「고치면 다음 실행부터」", g["keys"] == ["contract", "guide", "job", "form"] and g["open"] == [False, True, True, False]
              and g["src"] == ["코드에 든 글", "app/merge_guides_default/links.md", "jobs/plan_to_report.md", "코드에 든 글"] and "다음 실행부터 적용" in g["note"][1] and "다음 실행부터 적용" in g["note"][2]
              and "다음 실행부터" not in g["note"][0] + g["note"][3] and "자리 연결 LLM 검토의 판단 기준" in g["note"][1], [g["open"], g["src"], g["note"]])
        check("글은 줄바꿈 유지(pre-wrap) · 열 가로 넘침 없음", g["guide"].startswith("- 같은 표는 같게 잇는다\n- 특정 기관·차년도의 표") and g["ws"] == "pre-wrap" and g["over"] <= 1, [g["ws"], g["over"]])
        check("마지막으로 보낸 프롬프트 — 단위마다 한 줄(쪽 · 대상 · 글자 수) · 안 보낸 단위는 꺼짐", "마지막으로 보낸 프롬프트" in g["body"] and len(g["units"]) == 2 and "1–5쪽" in g["units"][0]["text"] and "대상 1" in g["units"][0]["text"]
              and "12,345자" in g["units"][0]["text"] and not g["units"][0]["disabled"] and g["units"][1]["disabled"] and "5쪽" in g["units"][1]["text"], g["units"])
        page.click("#headsDlgBody .lg-unit-head[data-unit='1']")
        page.wait_for_function("() => document.querySelectorAll('#headsDlgBody .lg-unit-body pre.lg-text').length === 2")
        u = page.evaluate("() => { const b = document.querySelector('#headsDlgBody .lg-unit-body'), ps = [...b.querySelectorAll('pre.lg-text')].map((x) => x.textContent), o = document.getElementById('headsDlgBody'); return { ps, over: o.scrollWidth - o.clientWidth, exp: document.querySelector('#headsDlgBody .lg-unit-head').getAttribute('aria-expanded') }; }")
        check("단위를 누르면 그 아래에 프롬프트 전체와 답(JSON 들여쓰기)", "## 자료(JSON)" in u["ps"][0] and '"summary": "없음"' in u["ps"][1] and u["exp"] == "true" and u["over"] <= 1
              and f"{a}/llm-guide/merge-links/prompt?unit=1" in guide_calls, [u, guide_calls])
        page.click("#headsDlgBody .lg-unit-head[data-unit='1']")
        check("다시 누르면 접힘(다시 읽지 않음)", page.evaluate("() => document.querySelector('#headsDlgBody .lg-unit-body').hidden") and sum("/prompt" in x for x in guide_calls) == 1, guide_calls)
        page.screenshot(path=str(OUT / "7g_llm_guide.png"))
        page.evaluate("() => { document.getElementById('taskStage').open = true; }")   # 이관이면 구분 기준 자리 표시는 프레임 묶음 안(2026-11-12 사용자 답 「1단계 안으로 옮김」 — 11-13 그 묶음이 2단계 「문서 프레임 작성」)
        check("이관 — 구분 기준 자리 표시 · 지원 양식 줄 · 코멘트가 2단계 「문서 프레임 작성」 묶음 안(변경 계획 아래 — #taskFrameApply)", page.evaluate("() => ['#divMarksBar', '#divBox .dv-profile', '#divComments'].every((q) => document.querySelector('#taskStage #taskFrameApply ' + q.replace('#divBox ', '')))"))
        page.click("#divMarksBar button[data-llm-guide=division-review]")
        page.wait_for_function("() => document.getElementById('headsDlgTitle').textContent === 'LLM 지침 — 구분 기준 LLM 재검토' && document.querySelectorAll('#headsDlgBody details.lg-part').length === 4")
        check("표시 줄의 「지침」 — 구분 기준 LLM 재검토의 지침 · 아직 실행한 적 없음 · 기본 모델 · 「빠진 자리 검토」 지침으로 바꾸는 단추 · 표시 줄은 1단계 묶음 안이라 강조 단추 없음(카드에 하나)", "아직 실행한 적 없음" in page.inner_text("#headsDlgBody")
              and "기본 모델" in page.inner_text("#headsDlgTools") and page.locator("#headsDlgTools button", has_text="「빠진 자리 검토」 지침").count() == 1
              and page.locator("#divMarksBar button.primary").count() == 0, page.inner_text("#headsDlgTools"))
        n_err = len(errors)
        page.locator("#headsDlgTools button", has_text="「빠진 자리 검토」 지침").click()
        page.wait_for_function("() => document.getElementById('headsDlgTitle').textContent === 'LLM 지침 — 빠진 자리 검토' && !!document.querySelector('#headsDlgBody .hwarn')")
        page.wait_for_timeout(100)
        expected = [e for e in errors[n_err:] if "404" in e and "Failed to load resource" in e]   # 흉내 낸 404 한 번이 콘솔에 남기는 줄 — 기대한 것(그 밖의 오류는 그대로 남겨 끝에서 잡는다)
        check("흉내 낸 404 는 콘솔에 한 줄뿐", len(expected) == 1 and len(errors) == n_err + 1, errors[n_err:])
        del errors[n_err:n_err + len(expected)]
        check("끝점이 없는 서버(404) — 「서버를 다시 시작한 뒤에 볼 수 있습니다(새 기능)」", "서버를 다시 시작한 뒤에 볼 수 있습니다(새 기능)" in page.inner_text("#headsDlgBody") and f"{a}/llm-guide/division-missing" in guide_calls, page.inner_text("#headsDlgBody"))
        page.unroute(GUIDE_URL)
        page.locator("#taskSteps button", has_text="연결 목록").click()
        page.locator("#headsDlgTools button", has_text="모두 4").click()
        rows = page.evaluate(ROWS)
        check("LLM 이 이은 줄에 「LLM」 꼬리표", rows[1]["status"] == "paired" and "LLM" in rows[1]["text"] and "고름" not in rows[1]["text"] and rows[1]["sel"] == "p901", rows[1])
        links["rev"] = page.evaluate("() => state.serverRev")
        page.locator("#taskSteps button", has_text="넣기 계획").click()
        page.wait_for_selector("#headsDlg[data-kind=fill] #headsDlgBody table")
        st = page.evaluate(STEPS)
        fill = page.eval_on_selector_all("#headsDlgBody tr", "trs => trs.map(t => t.textContent)")
        check("「넣기 계획」 — POST …/plan · 2열 「넣기 계획」(본문 항목·표) · ③ 줄에 수", links["calls"][-1] == ("POST", "/plan", None) and "넣기 계획" in page.inner_text("#headsDlgTitle")
              and any("주관" in x and "- (추진 내용)" in x and "넣음" in x for x in fill) and any("공동1" in x and "원본 없음" in x for x in fill) and any("정해진 자리" in x for x in fill)
              and "본문 1항목 · 표 칸 3 · 행 추가 1" in st[3]["text"] and st[3]["acts"] == ["넣기 계획 다시"] and st[4]["acts"] == ["계획 보기"]
              and [s["state"] for s in st[3:5]] == ["done", "now"] and [s["badge"] for s in st[3:5]] == ["완료", "다음 작업"], [fill, st[3:5]])
        check("넣기 계획 가로 넘침 없음", page.evaluate("() => { const b = document.getElementById('headsDlgBody'); return b.scrollWidth <= b.clientWidth + 1; }"))
        page.screenshot(path=str(OUT / "9a_fill_plan.png"))
        page.once("dialog", lambda dlg: dlg.accept())
        page.locator("#headsDlgFoot button", has_text="반영").click()
        page.wait_for_function("() => taskFlow.fill && taskFlow.fill.done && !state.busy", timeout=60000)
        st = page.evaluate(STEPS)
        check("「반영」 — 확인 뒤 POST …/apply {planId} · 열이 닫히고 ③④ 끝남(넣은 수)", links["calls"][-1] == ("POST", "/apply", {"planId": "pl1"}) and page.eval_on_selector("#headsDlg", "e => e.hidden")
              and [s["state"] for s in st][3:5] == ["done", "done"] and "본문 블록 3 · 표 칸 3 · 행 추가 1 · 템플릿 변환 0줄" in st[4]["text"], st[3:5])
        check("완료 뒤에도 번호 ①~⑥ 유지 · 완료와 준비 중을 글자로 구별 · ④ 뒤 ⑥ 작성요령 삭제", [s["no"] for s in st[1:]] == ["①", "②", "③", "④", "⑤", "⑥"]
              and [s["badge"] for s in st[1:6]] == ["완료", "완료", "완료", "완료", "준비 중"] and st[6]["state"] in ("now", "done"), st)
        page.evaluate("() => { window.journeyValues = structuredClone(dv.values); dv.values.orgs.lead += ' 변경'; taskStepsDraw(); }")
        check("완료 뒤 구성 값 변경 — 이전 넣기 결과가 있어도 선행 단계 먼저(2단계 「구성 맞추기」 가 현재)", page.evaluate("""() => taskFlow.fill.done && document.querySelector('#taskFlow [data-journey=frame]').dataset.state === 'now'
          && document.querySelector('#taskFlow [data-journey=map]').dataset.state === 'todo' && document.querySelector('#taskStage2 .dv-phase-state').textContent.includes('완료 후 진행')
          && document.querySelector('#taskStage2 [data-task-run]').disabled"""), page.evaluate(JOURNEY))
        page.evaluate("() => { dv.values = window.journeyValues; delete window.journeyValues; taskStepsDraw(); }")
        page.locator("#panel").screenshot(path=str(OUT / "9b_steps_applied.png"))
        page.unroute(LINKS_URL)
        page.locator("#panel").screenshot(path=str(OUT / "8_steps_done.png"))
        check("콘솔 오류 0", not errors, errors[:5])
        browser.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'FAIL ' + str(len(fails)) if fails else 'ALL PASS'}")
sys.exit(1 if fails else 0)
