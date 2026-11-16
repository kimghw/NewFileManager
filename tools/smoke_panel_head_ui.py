"""패널 머리(spec_작업 ② §10 「패널 머리」) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_panel_head_ui.py <그림·임시 폴더> [--port 18163]

작은 문서 둘(기술수요조사서 hwpx·docx)을 API 로 올려 본다: 패널 머리 첫 줄 = 작업 종류 목록(상단 바에는 없음) · 파일 이름 · ? · » /
둘째 줄 = 왼쪽 「에이전트」(hwpx) · 「작업 내용」 · 「<도구>」 | 오른쪽 접는 묶음 검증 · PDF · 기록 + 펼치기 단추(2026-11-16 — 처음엔 접힘: 묶음에서 고른 탭 하나만).
「작업 리스트」 는 상단 바 아이콘 #taskListBtn(2026-11-16 — 누르면 패널에 작업 리스트 · 눌림 · 다시 누르면 그 전 도구로).
작업 종류가 없으면 「작업 내용」만 숨긴다. 패널에서 「연구개발 프로젝트」를 고르면 그 내용이 열림(문서 위 탭 띠에 별도 탭은 없음).
· 펼치기·접기(기억) · 풀면 「검증」 으로 · 탭 띠를 접은 채로도 · 폭(520·430·320·280px — 펼침·접힘) · 접힌 띠 이름 · docx."""
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--port", type=int, default=18163)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"),
       "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:400] if detail != "" else ""), flush=True)
    if not ok:
        fails.append(name)


def upload(name):
    p = ROOT / "samples" / name
    return requests.post(f"{base}/api/docs?new=1", files={"file": (name, p.read_bytes())}, timeout=120).json()["docId"]


def open_work(page, wid):
    page.evaluate("(id) => { location.hash = '#w=' + id; }", wid)
    page.reload()
    page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=wid, timeout=120000)


def task_of(wid):
    return next(w for w in requests.get(f"{base}/api/works", timeout=10).json() if w["id"] == wid)["task"]


VIS = "(id) => { const e = document.getElementById(id); return !!e && !e.hidden && e.getClientRects().length > 0; }"
TOOL = "() => document.getElementById('panel').dataset.tool"
HEAD = "() => [document.getElementById('toolTitle').textContent, document.getElementById('toolTag').textContent]"  # 둘째 줄 — 도구 이름 · 꼬리표
# 머리와 그 안 것들의 자리(화면 px)
GEO = """() => { const h = document.querySelector('#panel .tool-heading'), r = (e) => { const b = e.getBoundingClientRect(); return [Math.round(b.left), Math.round(b.top), Math.round(b.right), Math.round(b.bottom)]; };
  return { head: r(h), over: h.scrollWidth - h.clientWidth, task: r(document.getElementById('panelTask')), fold: r(document.getElementById('panelFold')),
    title: r(document.getElementById('toolTitle')), tag: r(document.getElementById('toolTag')), tabs: r(document.getElementById('toolTabs')), pane: r(document.querySelector('#panel .pane:not([hidden])')) }; }"""
TABS = """() => { const t = document.getElementById('toolTabs'); return t && !t.hidden && t.getClientRects().length ? [...t.querySelectorAll('[role=tab]')].filter(b => !b.hidden && b.getClientRects().length).map((b) => [b.textContent, b.getAttribute('aria-selected')]) : null; }"""  # 둘째 줄의 실제 보이는 탭 — [[이름, 골랐나]] | None
NO_TAB = "() => !document.getElementById('tabDiv') && !document.querySelector('#workspaceNav .tab.active, #workspaceNav .tab[aria-selected=true]')"  # 탭 띠에 「연구개발과제」 탭이 없고 활성 탭도 없다
TOOL_NAME = {"Edits": "고친 문단", "Heads": "헤딩 추출"}
MORE = """() => { const r = (id) => document.getElementById(id).getBoundingClientRect(); return { agent: r('tabAgent').right, verify: r('tabVerify').left, last: r('tabLog').right, more: [r('toolMore').left, r('toolMore').right], head: r('panel').right }; }"""  # 펼친 묶음의 자리
NOLAP = """() => { const t = document.querySelector('.topbar'), r = [...t.children].filter((e) => e.getClientRects().length && !e.classList.contains('spacer')).map((e) => e.getBoundingClientRect());
  return t.scrollWidth <= t.clientWidth + 1 && r.every((x, i) => i === 0 || x.left >= r[i - 1].right - 1); }"""

def tabs_for(tool=None, selected="Verify", rnd=True, agent=True, open=True):
    """둘째 줄(2026-11-16) — 에이전트(hwpx) · 작업 내용(rnd) · 헤딩 추출(hwpx) · 표(늘 — 같은 날 탭 띠에서 옮긴 고정 탭) · <도구>(탭 띠 = 고친 문단 · 문서 비교에서 고른 적이 있으면) |
    검증 · PDF · 기록(접는 묶음 — 접히면 고른 탭 하나만 · 작업 리스트는 상단 바 아이콘). agent = hwpx(에이전트 · 헤딩 추출이 함께 보임).
    selected = agent|task|Heads|Tables|tool|Verify|Pdf|Log|None(작업 리스트를 볼 때 — 고른 탭 없음)"""
    more = [["검증", "Verify"], ["PDF", "Pdf"], ["기록", "Log"]]
    fixed = ([["헤딩 추출", "Heads"]] if agent else []) + [["테이블", "Tables"]]  # 탭 이름 「테이블」(2026-11-16 사용자 「표 아니고 테이블로」 — 전의 「표」)
    row = ([["에이전트", "agent"]] if agent else []) + ([["작업 내용", "task"]] if rnd else []) + fixed + ([[tool, "tool"]] if tool else []) + [m for m in more if open or m[1] == selected]
    return [[name, str(key == selected).lower()] for name, key in row]


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
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.goto(base)
        page.evaluate("() => { try { localStorage.clear(); } catch {} }")
        check("시작 화면(문서 없음) — 상단 바 「작업 리스트」 아이콘 감춤", not page.evaluate(VIS, "taskListBtn"))
        open_work(page, a)

        # ---- 1. 머리 첫 줄 — 작업 종류 목록(상단 바에는 없음) · 파일 이름 · ? · »
        opts = page.eval_on_selector_all("#panelTask option", "os => os.map(o => [o.value, o.textContent])")
        check("패널 머리에 작업 종류 목록 · 상단 바에는 없음(옛 #taskKind)", page.evaluate(VIS, "panelTask") and opts == [["", "작업 종류 선택"], ["rnd", "연구개발 프로젝트"], ["general", "일반 문서"]]
              and page.input_value("#panelTask") == "" and page.locator("#taskKind, .topbar select:not(#docSwitch)").count() == 0, opts)
        check("파일 이름 · 도움말(?) · 접기(»)", page.inner_text("#toolSource") == "기술수요조사서.hwpx" and page.locator("#toolHelp .panel-help").count() == 1
              and "원본을 읽고 저장한 결과" in page.get_attribute("#toolHelp .panel-help", "data-help") and page.evaluate(VIS, "panelFold"))
        for width in (1600, 1280, 1100):
            page.set_viewport_size({"width": width, "height": 800})
            page.wait_for_timeout(200)
            check(f"상단 바 넘침·겹침 없음({width}px)", page.evaluate(NOLAP))
        page.set_viewport_size({"width": 1600, "height": 900})

        # ---- 2. 둘째 줄 — 작업 종류 전에도 검증은 보이고 원래 도구 이름·꼬리표·설명은 숨김
        check("둘째 줄 = 탭(에이전트 · 접힌 묶음의 「검증」) · 도구 제목·꼬리표·설명 중복 없음", page.evaluate(HEAD) == ["검증", "파일·출력"] and not page.evaluate(VIS, "toolTitle") and not page.evaluate(VIS, "toolTag")
              and not page.evaluate(VIS, "toolDescription"), page.evaluate(HEAD))
        check("전체 도구 탭 중복 없음 · 작업 종류 전에는 「작업 내용」만 숨김 · 묶음은 처음에 접힘(고른 「검증」 만)", page.locator("#panelTabs").count() == 0 and page.evaluate(TABS) == tabs_for(rnd=False, open=False)
              and page.get_attribute("#toolMore", "aria-expanded") == "false", page.evaluate(TABS))
        g0 = page.evaluate(GEO)
        check("머리 높이 78px · 가로 넘침 없음 · 내용이 머리 바로 아래", g0["head"][3] - g0["head"][1] == 78 and g0["over"] <= 0 and g0["pane"][1] == g0["head"][3], g0)
        page.screenshot(path=str(OUT / "1_head.png"))

        check("탭 띠에는 에이전트·헤딩 추출·표·검증·PDF·기록이 없다(패널 머리로 옮김 — 2026-11-15 · 에이전트 · 헤딩 추출 · 표 2026-11-16)",
              page.evaluate("() => ['tabAgent', 'tabHeads', 'tabTables', 'tabVerify', 'tabPdf', 'tabLog'].every((id) => document.getElementById(id).closest('#toolTabs'))")
              and page.locator("#workspaceNav #tabAgent, #workspaceNav #tabHeads, #workspaceNav #tabTables, #workspaceNav #tabVerify, #workspaceNav #tabPdf, #workspaceNav #tabLog").count() == 0)
        # ---- 2-1. 오른쪽 묶음 펼치기·접기(2026-11-16 사용자 「검증/PDF/기록/작업리스트는 우측에 접어두고 클릭하면 펼치기」) — 펼친 상태는 기억
        page.click("#toolMore")
        g = page.evaluate(MORE)
        check("펼치기 — 검증 · PDF · 기록이 오른쪽(빈칸 뒤)에 · 단추는 줄 끝 · 기억", page.evaluate(TABS) == tabs_for(rnd=False) and page.get_attribute("#toolMore", "aria-expanded") == "true"
              and g["verify"] > g["agent"] + 20 and g["last"] <= g["more"][0] + 1 and g["more"][1] <= g["head"] and page.evaluate("() => localStorage.getItem('nfm.toolMore')") == "1"
              and page.evaluate(GEO)["over"] <= 0, [page.evaluate(TABS), g])
        page.locator("#panel .tool-heading").screenshot(path=str(OUT / "2_more_open.png"))
        page.click("#toolMore")
        check("접기 — 다시 고른 탭(검증) 하나만 · 기억", page.evaluate(TABS) == tabs_for(rnd=False, open=False) and page.evaluate("() => localStorage.getItem('nfm.toolMore')") == "0")
        page.locator("#panel .tool-heading").screenshot(path=str(OUT / "2_more_folded.png"))
        page.click("#tabAgent")
        check("접힌 채 「에이전트」 — 묶음 탭은 모두 감춤(단추만)", page.evaluate(TOOL) == "Agent" and page.evaluate(TABS) == tabs_for(rnd=False, open=False, selected="agent") and page.evaluate(VIS, "toolMore"), page.evaluate(TABS))
        page.focus("#tabAgent")
        page.keyboard.press("End")
        check("접힌 채 키보드 End — 보이는 마지막 탭(표 — 접힌 묶음의 탭은 건너뜀 · 2026-11-16 헤딩 추출 · 표가 고정 탭)", page.evaluate("() => document.activeElement.id") == "tabTables"
              and page.evaluate(TOOL) == "Tables", page.evaluate("() => document.activeElement.id"))
        page.click("#toolMore")
        page.click("#tabVerify")
        open_work(page, a)
        check("새로 읽어도 펼친 상태 그대로(기억)", page.evaluate(TABS) == tabs_for(rnd=False) and page.get_attribute("#toolMore", "aria-expanded") == "true", page.evaluate(TABS))
        # ---- 2-2. 「작업 리스트」 = 상단 바 아이콘(2026-11-16 사용자 「작업리스트는 우측 상단에 아이콘으로 넣어줘라」 — 패널 머리 묶음의 탭에서 옮김)
        PRESSED = "() => document.getElementById('taskListBtn').getAttribute('aria-pressed')"
        order = page.evaluate("() => [...document.querySelector('.topbar').children].map((e) => e.id).filter(Boolean)")
        check("상단 바 「작업 리스트」 아이콘 — 저장 다음 · 워크플로우 앞 · 글 없이 그림 · 이름은 title·aria-label · 패널 머리 탭은 없어짐",
              page.evaluate(VIS, "taskListBtn") and order.index("downloadBtn") < order.index("taskListBtn") < order.index("workflowLink")
              and page.inner_text("#taskListBtn").strip() == "" and page.locator("#taskListBtn svg").count() == 1 and page.get_attribute("#taskListBtn", "aria-label") == "작업 리스트"
              and page.locator("#toolTabList").count() == 0 and page.evaluate(PRESSED) == "false", order)
        page.click("#taskListBtn")
        check("누르면 패널에 작업 리스트 · 눌림 바탕 · 둘째 줄에 고른 탭 없음", page.evaluate(TOOL) == "Tasks" and page.evaluate(VIS, "paneTasks") and page.evaluate(PRESSED) == "true"
              and page.evaluate(TABS) == tabs_for(rnd=False, selected=None), page.evaluate(TABS))
        page.locator(".topbar").screenshot(path=str(OUT / "2_topbar_tasklist.png"))
        page.click("#taskListBtn")
        check("다시 누르면 그 전 도구(검증)로 · 눌림 풀림", page.evaluate(TOOL) == "Verify" and page.evaluate(PRESSED) == "false" and page.evaluate(TABS) == tabs_for(rnd=False))
        page.click("#tabPdf")
        page.click("#taskListBtn")
        page.click("#taskListBtn")
        check("그 전 도구가 PDF 면 PDF 로", page.evaluate(TOOL) == "Pdf" and page.evaluate(PRESSED) == "false")
        page.click("#tabVerify")
        page.click("#panelBtn")
        check("패널을 닫아도 아이콘은 보임 · 눌림 아님", page.evaluate("() => document.getElementById('panel').hidden") and page.evaluate(VIS, "taskListBtn") and page.evaluate(PRESSED) == "false")
        page.click("#taskListBtn")
        check("패널이 닫혀 있으면 열고 작업 리스트", not page.evaluate("() => document.getElementById('panel').hidden") and page.evaluate(TOOL) == "Tasks" and page.evaluate(PRESSED) == "true")
        page.click("#panelFold")
        check("패널을 접으면 눌림 풀림", page.evaluate("() => document.getElementById('panel').classList.contains('folded')") and page.evaluate(PRESSED) == "false")
        page.click("#taskListBtn")
        check("접힌 채 누르면 펴고 작업 리스트(그 전 도구로 가지 않음)", not page.evaluate("() => document.getElementById('panel').classList.contains('folded')") and page.evaluate(TOOL) == "Tasks"
              and page.evaluate(PRESSED) == "true")
        page.click("#tabVerify")
        check("다른 탭을 고르면 눌림 풀림", page.evaluate(TOOL) == "Verify" and page.evaluate(PRESSED) == "false")
        page.evaluate("() => { try { localStorage.setItem('nfm.panelFold', '0'); } catch {} }")  # 위에서 » 로 접은 기억(아이콘으로 편 것은 기억하지 않는다 — setPanel)을 지운다
        # ---- 3. 도구는 탭 띠(고친 문단·헤딩 추출·표)와 패널 머리 탭(기록·검증)에서 바꾼다 — 둘째 줄 값이 그 도구 이름으로 · 머리 높이는 그대로
        seen, moved = [], []
        for tool, pane in (("Edits", "paneEdits"), ("Log", "paneLog"), ("Heads", "paneHeads"), ("Tables", "paneTables"), ("Verify", "paneVerify")):
            page.click(f"#tab{tool}")
            page.wait_for_function("(t) => document.getElementById('panel').dataset.tool === t", arg=tool)
            seen.append(page.evaluate(HEAD)[0])
            g = page.evaluate(GEO)
            if not page.evaluate(VIS, pane) or g["head"] != g0["head"] or g["task"] != g0["task"] or g["fold"] != g0["fold"]:
                moved.append([tool, g["head"]])
        check("도구 바꾸기 — 둘째 줄이 도구 이름 · 머리 높이·첫 줄 자리 그대로", seen == ["고친 문단", "기록", "헤딩 추출", "테이블", "검증"] and not moved, [seen, moved])

        # ---- 4. 패널에서 작업 = 연구개발과제 → 저장 · 그 내용이 바로 열림(탭 띠에 탭은 안 생긴다 — 2026-11-12)
        check("작업 종류를 고르기 전 — 헤딩 추출·표·<도구>(마지막 탭 띠 도구 「고친 문단」)·검증·PDF·기록", page.evaluate(TABS) == tabs_for(tool="고친 문단", rnd=False) and not page.evaluate(VIS, "toolTitle"), page.evaluate(TABS))
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task") and r.request.method == "PUT") as put:
            page.select_option("#panelTask", "rnd")
        page.wait_for_selector("#divBox .dv-task select")
        check("연구개발 프로젝트 선택 — 저장·작업 내용 열림 · 작업 내용/검증 표시", put.value.status == 200 and page.evaluate(TOOL) == "Div" and page.evaluate(VIS, "paneDiv")
              and page.evaluate(NO_TAB) and page.evaluate(TABS) == tabs_for(tool="고친 문단", selected="task") and not page.evaluate(VIS, "toolTitle") and page.evaluate(HEAD) == ["작업 내용", "프로젝트 · TASK"], page.evaluate(TABS))
        check("활성 탭이 없어도 Tab 키는 탭 띠의 보이는 첫 탭(고친 문단)이 받는다", page.evaluate("() => [...document.querySelectorAll('#workspaceNav .tab')].filter((t) => t.tabIndex === 0).map((t) => t.id)") == ["tabEdits"])
        g = page.evaluate(GEO)
        check("연구개발과제 내용 — 머리 높이 78px 그대로", g["head"] == g0["head"] and g["pane"][1] == g["head"][3], g["head"])
        check("작업에 저장", task_of(a)["kind"] == "rnd", task_of(a))
        check("연구개발과제 패널 첫 카드에는 「작업」 칸이 없다(패널 머리의 목록 하나뿐 — 2026-11-12)", page.locator("#divBox .dv-task select[data-task=kind]").count() == 0
              and page.locator("#divBox .dv-task select[data-task=job]").count() == 1)
        page.locator("#panel").screenshot(path=str(OUT / "4_panel_rnd.png"))

        # ---- 5. 탭 띠로 다른 도구를 봐도 작업 목록은 그대로 · 둘째 줄 탭 「작업 내용」 으로 돌아옴
        page.click("#tabVerify")
        check("패널 머리 「검증」 — 작업 목록은 그대로 「연구개발과제」", page.evaluate(TOOL) == "Verify" and page.input_value("#panelTask") == "rnd" and page.evaluate(HEAD)[0] == "검증")
        g = page.evaluate(GEO)
        check("다른 도구를 볼 때 — 검증 선택·작업 내용 유지 · 머리 높이 그대로", page.evaluate(TABS) == tabs_for(tool="고친 문단")
              and g["tabs"][0] >= g["head"][0] and g["tabs"][2] <= g["head"][2] and g["tabs"][1] >= g["task"][3] and g["head"] == g0["head"] and g["over"] <= 0, [page.evaluate(TABS), g])
        page.locator("#panel .tool-heading").screenshot(path=str(OUT / "5_head_tabs.png"))
        page.click("#toolTabTask")
        check("탭 「작업 내용」 — 그 내용 · 그 탭을 고름", page.evaluate(TOOL) == "Div" and page.evaluate(VIS, "paneDiv") and page.evaluate(TABS) == tabs_for(tool="고친 문단", selected="task") and page.evaluate(NO_TAB))
        page.click("#tabPdf")
        check("탭 「PDF」 — PDF 를 고름", page.evaluate(TOOL) == "Pdf" and page.evaluate(TABS) == tabs_for(tool="고친 문단", selected="Pdf"), page.evaluate(TABS))
        page.click("#tabVerify")
        check("탭 「검증」 — 검증으로 돌아감", page.evaluate(TOOL) == "Verify" and page.evaluate(TABS) == tabs_for(tool="고친 문단"))
        page.click("#toolTabTask")

        # ---- 6. 풀기 — 패널의 목록에서 풀면 「검증」 으로(돌아가는 단추도 없음) · 다시 고르면 다시 열림
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task")):
            page.select_option("#panelTask", "")
        check("패널에서 풀면 — 검증으로 · 검증 탭 유지", page.evaluate(TABS) == tabs_for(tool="고친 문단", rnd=False) and not page.evaluate(VIS, "toolTitle") and page.evaluate(TOOL) == "Verify" and page.evaluate(HEAD)[0] == "검증"
              and task_of(a)["kind"] == "", page.evaluate(HEAD))
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task")):
            page.select_option("#panelTask", "rnd")
        page.wait_for_selector("#divBox .dv-task select")
        check("패널에서 다시 고르면 — 그 내용이 다시 열림", page.evaluate(TOOL) == "Div" and page.evaluate(VIS, "paneDiv"))
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task")):
            page.select_option("#panelTask", "")
        check("한 번 더 풀어도 같다", page.evaluate(TOOL) == "Verify" and page.evaluate(TABS) == tabs_for(tool="고친 문단", rnd=False) and task_of(a)["kind"] == "")
        check("풀린 문서에서는 showTab('Div') 도 안 열린다", page.evaluate("() => { showTab('Div'); return document.getElementById('panel').dataset.tool; }") == "Verify")

        # ---- 7. 탭 띠를 접은 채로도(상단 바 「탭 ▴」) 패널의 작업 목록으로 연구개발과제 내용을 연다
        page.click("#navFold")
        check("탭 띠 접힘", page.evaluate("() => document.getElementById('workspaceNav').getClientRects().length") == 0)
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task")):
            page.select_option("#panelTask", "rnd")
        page.wait_for_selector("#divBox .dv-task select")
        check("탭 띠를 접은 채 프로젝트 선택 — 작업 내용 열림", page.evaluate(TOOL) == "Div" and page.evaluate(VIS, "paneDiv") and page.evaluate(HEAD)[0] == "작업 내용")
        page.evaluate("() => showTab('Edits')")  # 탭 띠가 접힌 채 다른 도구로 넘어간 꼴(고친 문단 배지 · 쪽 번호를 눌러 PDF 가 열림 …)
        check("탭 띠를 접은 채 다른 도구 — 고친 문단 선택·작업 내용 유지", page.evaluate(TOOL) == "Edits" and page.evaluate(TABS) == tabs_for(tool="고친 문단", selected="tool"), page.evaluate(TABS))
        page.click("#toolTabTask")
        check("탭 띠를 접은 채로도 탭 「작업 내용」 으로 돌아옴(옛 미결 — 탭 띠를 접으면 길이 없었다) · 도구 탭은 마지막 도구", page.evaluate(TOOL) == "Div" and page.evaluate(VIS, "paneDiv")
              and page.evaluate(TABS) == tabs_for(tool="고친 문단", selected="task"), page.evaluate(TABS))
        page.click("#toolTabTool")
        check("도구 탭 — 마지막 도구(고친 문단)로", page.evaluate(TOOL) == "Edits")
        page.click("#toolTabTask")
        page.click("#navFold")
        check("펴도 탭 띠에 「연구개발과제」 탭·활성 탭 없음", page.evaluate(NO_TAB) and page.evaluate(VIS, "tabEdits"))

        # ---- 8. 폭 — 520 · 430 · 320 · 280px: 머리 높이 78px 그대로 · 가로 넘침 없음 · 목록·단추·이름이 머리 안
        for width in (520, 430, 320, 280):
            page.evaluate("(w) => { const c = colSizers.find((x) => x.box === 'panel'); c.w = w; c.apply(); }", width)
            page.wait_for_timeout(300)
            g = page.evaluate(GEO)
            check(f"패널 {width}px — 높이 78px · 넘침 없음 · 머리 안", g["head"][2] - g["head"][0] in (width - 1, width) and g["head"][3] - g["head"][1] == 78 and g["over"] <= 0
                  and g["task"][0] >= g["head"][0] and g["fold"][2] <= g["head"][2] and g["tabs"][2] <= g["head"][2] and g["tabs"][0] >= g["head"][0] and g["pane"][1] == g["head"][3], g)
            page.locator("#panel").screenshot(path=str(OUT / f"8_panel_{width}.png"))
        # 도구 탭 이름이 긴 「고친 문단」·「헤딩 추출」 에서도 좁은 폭에 넘치지 않는다 — 펼친 탭 여섯(에이전트 · 작업 내용 · <도구> · 검증 · PDF · 기록 — 작업 리스트는 상단 바로 뺌) · 접으면 셋
        for tool in ("Edits", "Heads"):
            page.click(f"#tab{tool}")
            for width in (320, 280):
                page.evaluate("(w) => { const c = colSizers.find((x) => x.box === 'panel'); c.w = w; c.apply(); }", width)
                page.wait_for_timeout(300)
                g = page.evaluate(GEO)
                check(f"{tool} · 패널 {width}px — 탭 여덟 머리 안 · 높이 78px · 넘침 없음", len(page.evaluate(TABS) or []) == 8 and (page.evaluate(TABS) or [[0, 0]])[0][0] == "에이전트" and g["head"][3] - g["head"][1] == 78 and g["over"] <= 0
                      and g["tabs"][2] <= g["head"][2] and g["tabs"][0] >= g["head"][0] and g["pane"][1] == g["head"][3], g)
            page.locator("#panel").screenshot(path=str(OUT / f"8_panel_280_{tool}.png"))
            page.click("#toolMore")  # 접으면 — 에이전트 · 작업 내용 · <도구>(고른 탭)
            g, tl = page.evaluate(GEO), page.evaluate(TABS)
            check(f"{tool} · 패널 280px 접힘 — 탭 다섯 · 넘침 없음 · 머리 안", [t[0] for t in tl] == ["에이전트", "작업 내용", "헤딩 추출", "테이블", "고친 문단"] and g["over"] <= 0
                  and g["tabs"][2] <= g["head"][2] and g["head"][3] - g["head"][1] == 78, [tl, g])
            page.locator("#panel").screenshot(path=str(OUT / f"8_panel_280_{tool}_folded.png"))
            page.click("#toolMore")
        page.evaluate("() => { const c = colSizers.find((x) => x.box === 'panel'); c.w = null; c.apply(); }")

        # ---- 9. 문서 비교(전체 폭) — 머리 꼴은 같고 파일 이름 자리는 「여러 문서 …」
        page.click("#tabCompare")
        g = page.evaluate(GEO)
        check("문서 비교 — 둘째 줄 「문서 비교」 · 넘침 없음 · 작업 목록 그대로", page.evaluate(HEAD)[0] == "문서 비교" and g["over"] <= 0 and page.inner_text("#toolSource") == "여러 문서 · 저장된 분석 결과"
              and page.input_value("#panelTask") == "rnd", [page.evaluate(HEAD), g["over"]])
        page.screenshot(path=str(OUT / "9_compare.png"))
        page.click("#toolTabTask")

        # ---- 10. 접힌 띠 이름 = 지금 보는 도구 이름
        page.click("#panelFold")
        rail = page.inner_text("#panelRail .col-rail-name")
        check("패널을 접으면 띠 이름 = 「작업 내용」", rail == "작업 내용" and page.evaluate("() => document.getElementById('panel').classList.contains('folded')"), rail)
        page.click("#panelRail")
        check("띠를 누르면 펴지고 머리 그대로", page.evaluate(VIS, "panelTask") and page.evaluate(TOOL) == "Div")

        # ---- 11. docx — 작업 종류는 문서마다
        open_work(page, b)
        check("docx — 작업 종류 안 고름 · 「에이전트」 없음 · 검증 표시 · 상단 바 「작업 리스트」 아이콘", page.input_value("#panelTask") == "" and page.evaluate(TABS) == tabs_for(rnd=False, agent=False) and page.evaluate(HEAD)[0] == "검증"
              and page.evaluate(VIS, "taskListBtn"), page.evaluate(TABS))
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
