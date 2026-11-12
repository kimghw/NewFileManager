"""상단 로고 = 시작 화면으로(spec_작업 ② §7 「시작 화면으로」) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_home_ui.py <그림·임시 폴더> [--port 18179]

- 시작 화면: 로고는 링크(`#homeLink`), 눌러도 그대로(다시 읽지 않음).
- 작업을 연 뒤(표를 고르고 2열 「작성요령 · 표 지침」 을 연 채) 로고 → 시작 화면 · 주소의 `#w=` 걷힘 · 표 손잡이·2열·패널·도구 줄이 남지 않음 · 최근 작업에 그 작업 · 작업은 안 지워짐 ·
  화면을 다시 읽지 않음. 새로 고쳐도 시작 화면, 최근 작업에서 다시 열면 같은 작업.
- 묻는 때: 2열에 저장 안 한 표 지침 글 · 서버에 반영 안 된 수정(「취소」 면 그대로, 「확인」 이면 시작 화면).
- 키보드(초점 + Enter) · Ctrl 누름(새 탭에 시작 화면, 지금 작업은 그대로) · 좁은 창(앱 이름 글이 숨어도 아이콘은 남음).
- TASK 카드(spec_작업 ② §15 — 7-1): 다섯 장·차례·글·로고(그림·바탕색)·줄 수(넓은 창 5 · 860px 3 · 560px 2 · 400px 1) · 준비 중 카드 · 누르면 파일 고르기 → 그 TASK 로 작업 내용 ·
  같은 파일로 하던 작업 이어 열기(다른 TASK 면 안 바꿈 · 「새 작업으로 열기」) · 카드에 파일 놓기(docx 안 받음 · hwpx 는 양식 판정대로)."""
import argparse
import base64
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
ap.add_argument("--port", type=int, default=18179)
args = ap.parse_args()
OUT = Path(args.out).resolve()
SMALL = "기술수요조사서.hwpx"
PLAN = "연구개발계획서_양식.hwpx"  # 국가R&D 양식 — 양식 판정이 첨부 파일 종류(사업계획서)를 정한다(TASK 카드 7-1)

OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)  # 앞 돌림의 작업을 비우고 시작(같은 예제는 이어 열린다)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"),
       "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails, dialogs = [], [], []
answer = {"accept": True}


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:400] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def on_dialog(d):
    dialogs.append(d.message)
    if answer["accept"]:
        d.accept()
    else:
        d.dismiss()


def open_sample(page, name, timeout=240000):
    page.evaluate("() => { const s = document.getElementById('sampleSection'); s.hidden = false; s.open = true; }")
    page.evaluate("(n) => document.querySelector(`.sample[aria-label=\"예제 ${n} 열기\"]`).click()", name)
    page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=timeout)


# 시작 화면인가 — 보이는 것·감춘 것·주소·남은 표 손잡이
HOME = """() => { const vis = (e) => !!e && !e.hidden && e.getClientRects().length > 0, g = (id) => document.getElementById(id);
  return { id: state.id, hash: location.hash, path: location.pathname, noDoc: document.body.classList.contains('no-doc'), empty: vis(g('empty')), drop: vis(g('drop')),
    scroller: vis(g('scroller')), nav: vis(g('workspaceNav')), bar: vis(g('docBar')), panel: vis(g('panel')), col: vis(g('headsDlg')), peer: vis(g('peerCol')), file: vis(g('fileInfo')),
    barCtl: vis(g('barCtl')), panelBtn: vis(g('panelBtn')), save: vis(g('downloadBtn')), verify: vis(g('verifyBtn')),
    corners: [...document.querySelectorAll('.tbl-corner, .tbl-corner-guide')].filter(vis).length, menu: [...document.querySelectorAll('.ctx-menu')].filter(vis).length,
    doc: g('doc').childElementCount, saveState: g('saveState').textContent, mark: window.__mark || 0 }; }"""
FIRST_DONE = "() => typeof heads !== 'undefined' && heads.view && heads.view.stage2 && heads.view.stage3 && !(heads.view.job && heads.view.job.status === 'running')"


def is_home(h):
    return (h["id"] is None and h["hash"] == "" and h["path"] == "/" and h["noDoc"] and h["empty"] and h["drop"]
            and not any(h[k] for k in ("scroller", "nav", "bar", "panel", "col", "peer", "file", "barCtl", "panelBtn", "save", "verify"))
            and h["corners"] == 0 and h["menu"] == 0 and h["doc"] == 0)


def go_home(page):
    page.locator("#homeLink").click()
    page.wait_for_timeout(400)
    return page.evaluate(HOME)


def reopen(page, wid):
    page.locator(f"#workList .recent-work-open[title$='작업 {wid}']").click()
    page.wait_for_function("(w) => state.id === w && document.querySelector('#doc .sheet .para') != null", arg=wid, timeout=60000)
    page.wait_for_timeout(300)


try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("dialog", on_dialog)
        page.goto(base)
        page.wait_for_selector("#drop")

        # ---- 1. 시작 화면 — 로고는 링크, 눌러도 그대로
        logo = page.evaluate("""() => { const a = document.getElementById('homeLink'), cs = getComputedStyle(a);
            return { tag: a.tagName, cls: a.className, href: a.getAttribute('href'), label: a.getAttribute('aria-label'), title: a.title, cursor: cs.cursor, deco: cs.textDecorationLine,
                     text: a.textContent.trim(), w: a.getBoundingClientRect().width }; }""")
        check("로고는 링크(a.brand · href=/ · 이름에 「시작 화면으로」)", logo["tag"] == "A" and logo["cls"] == "brand" and logo["href"] == "/" and "시작 화면으로" in logo["label"]
              and "시작 화면으로" in logo["title"] and logo["text"] == "HWPX·DOCX 웹 편집" and logo["deco"] == "none", logo)
        check("시작 화면에서는 손가락 커서가 아님", logo["cursor"] == "default", logo["cursor"])
        page.evaluate("() => { window.__mark = 1; }")  # 화면을 다시 읽으면 사라진다
        h = go_home(page)
        check("시작 화면에서 로고를 눌러도 그대로(다시 읽지 않음)", is_home(h) and h["mark"] == 1, h)
        page.screenshot(path=str(OUT / "1_start.png"))

        # ---- 2. 작업을 열고(표를 고르고 2열을 연 채) 로고 → 시작 화면
        open_sample(page, SMALL)
        page.wait_for_function(FIRST_DONE, timeout=120000)
        page.wait_for_timeout(500)
        wid = page.evaluate("() => state.id")
        check("작업을 열면 주소에 #w=<id>", page.evaluate("() => location.hash") == f"#w={wid}")
        check("작업 화면에서는 손가락 커서", page.evaluate("() => getComputedStyle(document.getElementById('homeLink')).cursor") == "pointer")
        tid = page.evaluate("() => { const t = document.querySelector('#doc table.tbl[data-tbl] td .para'); return t ? t.closest('table.tbl').dataset.tbl : null; }")
        check("예제에 표가 있음", bool(tid), tid)
        page.locator(f"#doc table.tbl[data-tbl='{tid}'] td .para").first.click()
        page.wait_for_selector(f".tbl-corner[data-for='{tid}']")
        page.locator(".tbl-corner-guide").click()
        page.wait_for_function("() => heads.dlg === 'tableAgent' && !!document.querySelector('.ta-wrap')", timeout=30000)
        page.locator("#homeLink").hover()
        page.wait_for_timeout(350)
        before = page.evaluate(HOME)
        check("가기 전 — 문서·2열·패널·표 손잡이 2개가 보임", before["scroller"] and before["col"] and before["panel"] and before["corners"] == 2 and before["mark"] == 1, before)
        check("로고에 올리면 옅은 바탕", page.evaluate("() => getComputedStyle(document.getElementById('homeLink')).backgroundColor") not in ("rgba(0, 0, 0, 0)", "transparent"))
        page.screenshot(path=str(OUT / "2_work.png"))
        dialogs.clear()
        h = go_home(page)
        check("로고 → 시작 화면(문서·도구 줄·2열·패널·표 손잡이 없음 · 주소의 #w= 걷힘)", is_home(h), h)
        check("묻지 않고 감(저장 안 한 것이 없음)", dialogs == [], dialogs)
        check("화면을 다시 읽지 않음", h["mark"] == 1, h["mark"])
        check("상단 저장 상태 글 없음", h["saveState"] == "", h["saveState"])
        page.wait_for_selector(f"#workList .recent-work-open[title$='작업 {wid}']")
        check("최근 작업에 그 작업 — 「지금」 표시는 없음", page.evaluate("(w) => { const b = document.querySelector(`#workList .recent-work-open[title$='작업 ${w}']`); return !!b && !b.closest('li').classList.contains('current'); }", wid))
        check("작업은 지워지지 않음(GET /api/works)", any(w["id"] == wid for w in requests.get(f"{base}/api/works", timeout=10).json()))
        check("시작 화면의 로고는 다시 기본 커서", page.evaluate("() => getComputedStyle(document.getElementById('homeLink')).cursor") == "default")
        page.screenshot(path=str(OUT / "3_home.png"))

        # ---- 3. 새로 고쳐도 시작 화면 · 최근 작업에서 다시 열면 같은 작업
        page.reload()
        page.wait_for_selector("#workList .recent-work-open")
        page.wait_for_timeout(600)
        h = page.evaluate(HOME)
        check("새로 고쳐도 시작 화면(작업이 저절로 열리지 않음)", is_home(h) and h["mark"] == 0, h)
        reopen(page, wid)
        h = page.evaluate(HOME)
        check("최근 작업에서 다시 열면 같은 작업 · 주소에 #w=", h["id"] == wid and h["hash"] == f"#w={wid}" and h["scroller"] and not h["empty"] and not h["noDoc"] and h["doc"] > 0, h)
        page.mouse.move(700, 20)  # 최근 작업 줄을 누른 자리에 표가 그려지면 올린 표로 손잡이가 뜬다 — 마우스를 상단 바로 치우고 본다
        page.wait_for_timeout(450)
        h, sel = page.evaluate(HOME), page.evaluate("() => ({ active: tmn.active, hover: tmn.hover })")
        check("다시 연 작업에 고른 표·표 손잡이·2열이 남아 있지 않음", h["corners"] == 0 and not h["col"] and sel == {"active": None, "hover": None}, (h, sel))

        # ---- 4. 2열에 저장 안 한 표 지침 글 — 묻는다(취소 = 그대로 · 확인 = 시작 화면)
        page.locator(f"#doc table.tbl[data-tbl='{tid}'] td .para").first.click()
        page.wait_for_selector(f".tbl-corner[data-for='{tid}']")
        page.locator(".tbl-corner-guide").click()
        page.wait_for_function("() => heads.dlg === 'tableAgent' && !!document.querySelector('.ta-wrap')", timeout=30000)
        ta = page.locator("#headsDlgBody textarea").first
        ta.click()
        ta.fill("저장 안 한 글")
        check("2열에 저장 안 한 글이 생김", page.evaluate("() => !!heads.xl.agent && heads.xl.agent.dirty()"))
        answer["accept"] = False
        dialogs.clear()
        h = go_home(page)
        check("저장 안 한 표 지침 — 묻고, 취소하면 그대로(2열·글 유지)", len(dialogs) == 1 and "표 지침" in dialogs[0] and h["id"] == wid and h["col"] and h["scroller"]
              and page.evaluate("() => document.querySelector('#headsDlgBody textarea').value") == "저장 안 한 글", (dialogs, h))
        answer["accept"] = True
        dialogs.clear()
        h = go_home(page)
        check("저장 안 한 표 지침 — 확인하면 시작 화면", len(dialogs) == 1 and is_home(h), (dialogs, h))

        # ---- 5. 서버에 반영 안 된 수정 — 묻는다(반영 실패한 문단이 있는 꼴로)
        reopen(page, wid)
        page.evaluate("() => { state.failed.add('zz-home-check'); }")
        answer["accept"] = False
        dialogs.clear()
        h = go_home(page)
        check("반영 안 된 수정 — 묻고(「시작 화면으로 가면」), 취소하면 그대로", len(dialogs) == 1 and "시작 화면으로 가면" in dialogs[0] and h["id"] == wid and h["scroller"], (dialogs, h))
        answer["accept"] = True
        dialogs.clear()
        h = go_home(page)
        check("반영 안 된 수정 — 확인하면 시작 화면", len(dialogs) == 1 and is_home(h), (dialogs, h))
        check("시작 화면에서는 창을 닫을 때 묻지 않음(hasUnsaved 꺼짐)", page.evaluate("() => hasUnsaved()") is False)

        # ---- 6. 키보드(초점 + Enter)
        reopen(page, wid)
        page.locator("#homeLink").focus()
        page.keyboard.press("Enter")
        page.wait_for_timeout(400)
        check("키보드 — 로고에 초점 + Enter → 시작 화면", is_home(page.evaluate(HOME)), page.evaluate(HOME))

        # ---- 7. Ctrl 누름 = 새 탭에 시작 화면(지금 작업은 그대로)
        reopen(page, wid)
        with page.context.expect_page() as pop:
            page.locator("#homeLink").click(modifiers=["Control"])
        tab = pop.value
        tab.wait_for_selector("#workList .recent-work-open")
        tab.wait_for_timeout(500)
        th, h = tab.evaluate(HOME), page.evaluate(HOME)
        check("Ctrl 누름 — 새 탭은 시작 화면", is_home(th), th)
        check("Ctrl 누름 — 지금 탭의 작업은 그대로", h["id"] == wid and h["hash"] == f"#w={wid}" and h["scroller"] and not h["empty"], h)
        tab.close()

        # ---- 7-1. TASK 카드(spec_작업 ② §15) — 다섯 장 · 로고 · 누르면 파일 고르기 → 그 TASK 로 작업 내용 · 카드에 파일 놓기
        h = go_home(page)
        check("TASK 카드 — 시작 화면으로", is_home(h), h)
        CARDS = """() => [...document.querySelectorAll('#taskCards .task-card')].map((b) => { const r = b.getBoundingClientRect(), lg = b.querySelector('.task-logo'), u = lg.querySelector('use');
            return { key: b.dataset.task, doc: b.querySelector('.task-card-doc').textContent, name: b.querySelector('.task-card-name').textContent, go: b.querySelector('.task-card-go').textContent.trim(),
                     soon: b.getAttribute('aria-disabled') === 'true', busy: b.classList.contains('busy'), top: Math.round(r.top), h: Math.round(r.height), w: Math.round(r.width),
                     sym: !!document.querySelector(u.getAttribute('href')), ink: Math.round(u.getBBox().width), tone: lg.dataset.doc, bg: getComputedStyle(lg).backgroundImage, logo: Math.round(lg.getBoundingClientRect().width) }; })"""
        cards = page.evaluate(CARDS)
        check("TASK 카드 다섯 장 — 할 일 차례(일의 흐름)", [c["key"] for c in cards] == ["plan_fit", "plan_merge", "plan_to_report", "report_fit", "report_merge"], [c["key"] for c in cards])
        check("카드 글 = 문서 / 동작 두 줄", [(c["doc"], c["name"]) for c in cards] == [("사업계획서", "양식 맞추기"), ("사업계획서", "취합"), ("사업계획서 → 연차보고서", "이관"),
                                                                             ("연차보고서", "양식 맞추기"), ("연차보고서", "취합")], [(c["doc"], c["name"]) for c in cards])
        check("TASK 마다 로고(그림 있음 · 46px · 바탕 그라데이션)", all(c["sym"] and c["ink"] >= 20 and c["logo"] == 46 and "gradient" in c["bg"] for c in cards), cards)
        check("로고 바탕색 = 문서(사업계획서 둘 같음 · 이관 다름 · 연차보고서 둘 같음)", [c["tone"] for c in cards] == ["plan", "plan", "plan-report", "report", "report"]
              and cards[0]["bg"] == cards[1]["bg"] and cards[3]["bg"] == cards[4]["bg"] and len({cards[0]["bg"], cards[2]["bg"], cards[3]["bg"]}) == 3, [(c["tone"], c["bg"]) for c in cards])
        check("로고 그림은 TASK 마다 다름", page.evaluate("() => new Set([...document.querySelectorAll('.task-icons symbol')].map((s) => s.innerHTML.replace(/\\s+/g, ''))).size") == 5)
        check("넓은 창 — 다섯 장이 한 줄 · 같은 높이 · 가로 넘침 없음", len({c["top"] for c in cards}) == 1 and len({c["h"] for c in cards}) == 1
              and page.evaluate("() => { const e = document.getElementById('empty'); return e.scrollWidth <= e.clientWidth + 1; }"), [(c["top"], c["h"], c["w"]) for c in cards])
        check("준비 중인 TASK 는 「연차보고서 취합」 하나", [c["key"] for c in cards if c["soon"]] == ["report_merge"] and cards[4]["go"] == "준비 중" and cards[0]["go"].startswith("사업계획서 올려 시작"),
              [(c["key"], c["soon"], c["go"]) for c in cards])
        order = page.evaluate("""() => ['.home-intro', '#homeTasks', '.home-capabilities', '#recent'].map((s) => Math.round(document.querySelector(s).getBoundingClientRect().top))""")
        check("자리 — 올리기 묶음 아래 · 기능 소개 줄 위 · 제목 「TASK」", order == sorted(order) and len(set(order)) == 4 and page.evaluate("() => document.getElementById('homeTasksTitle').textContent") == "TASK", order)
        page.screenshot(path=str(OUT / "7_tasks.png"), full_page=True)
        for width, cols in ((860, 3), (560, 2), (400, 1)):  # 좁은 창 — 카드 줄 수가 준다(가로 넘침 없음)
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(250)
            cs = page.evaluate(CARDS)
            fit = page.evaluate("() => { const e = document.getElementById('empty'), w = e.clientWidth; return e.scrollWidth <= w + 1 && [...document.querySelectorAll('#taskCards .task-card *')].every((x) => x.getBoundingClientRect().right <= w + 1); }")
            check(f"창 {width}px — 한 줄에 {cols}장 · 넘침 없음", len([c for c in cs if c["top"] == cs[0]["top"]]) == cols and fit, [(c["top"], c["w"]) for c in cs])
            page.locator("#homeTasks").scroll_into_view_if_needed()
            page.screenshot(path=str(OUT / f"7_tasks_{width}.png"))
        page.set_viewport_size({"width": 1500, "height": 1000})
        page.wait_for_timeout(250)

        TASK = "() => ({ id: state.id, task: state.task, tool: document.getElementById('panel').dataset.tool, pane: !document.getElementById('paneDiv').hidden, " \
               "job: (document.querySelector('#paneDiv select[data-task=job]') || {}).value, toast: document.getElementById('toast').hidden ? '' : document.getElementById('toast').textContent })"
        page.locator("#taskCards [data-task=report_merge]").click(force=True)  # aria-disabled 라 Playwright 는 「못 누르는 것」 으로 본다 — 사람이 누르는 것처럼 그대로 누른다
        page.wait_for_timeout(300)
        t = page.evaluate(TASK)
        check("준비 중 카드 — 누르면 알림만(작업이 안 열림)", t["id"] is None and "준비 중" in t["toast"], t)

        with page.expect_file_chooser() as fc:  # 누르면 파일 고르기 — 같은 파일로 하던 작업(2 에서 연 것)이 있으니 그 작업을 그 TASK 로 이어 연다
            page.locator("#taskCards [data-task=plan_fit]").click()
        check("카드 누름 → 파일 고르기(hwp·hwpx)", fc.value.element.evaluate("(e) => e.accept") == ".hwp,.hwpx")
        fc.value.set_files(str(ROOT / "samples" / SMALL))
        page.wait_for_function("(w) => state.id === w && document.getElementById('panel').dataset.tool === 'Div' && !!document.querySelector('#paneDiv select[data-task=job]')", arg=wid, timeout=60000)
        page.wait_for_function("() => state.task.job === 'plan_fit' && worksList.some((w) => w.id === state.id && (w.task || {}).job === 'plan_fit')", timeout=30000)
        t = page.evaluate(TASK)
        check("그 TASK 로 열림 — 작업 종류 연구개발과제 · 할 일 · 양식 판정이 못 정한 종류는 그 TASK 의 문서", t["task"] == {"kind": "rnd", "file": "plan", "job": "plan_fit", "project": ""}, t["task"])
        check("작업 내용(연구개발과제 패널)이 열리고 「할 일」 칸이 그 TASK", t["tool"] == "Div" and t["pane"] and t["job"] == "plan_fit", t)
        check("이어 연 작업 — 알림에 TASK 이름 · 「새 작업으로 열기」", "이어서 엽니다" in t["toast"] and "사업계획서 양식 맞추기" in t["toast"] and "새 작업으로 열기" in t["toast"], t["toast"])
        saved = next((w for w in requests.get(f"{base}/api/works", timeout=10).json() if w["id"] == wid), {})
        check("작업에 저장됨(GET /api/works)", (saved.get("task") or {}).get("job") == "plan_fit" and saved["task"]["kind"] == "rnd", saved.get("task"))
        page.screenshot(path=str(OUT / "7_task_open.png"))

        h = go_home(page)  # 다른 TASK 카드로 같은 파일 — 하던 작업의 TASK 는 안 바꾼다
        with page.expect_file_chooser() as fc:
            page.locator("#taskCards [data-task=plan_merge]").click()
        fc.value.set_files(str(ROOT / "samples" / SMALL))
        page.wait_for_function("(w) => state.id === w && document.getElementById('panel').dataset.tool === 'Div' && !document.getElementById('toast').hidden", arg=wid, timeout=60000)
        t = page.evaluate(TASK)
        check("다른 TASK 로 하던 작업 — 그대로 이어 엶(할 일 안 바뀜) · 알림", t["task"]["job"] == "plan_fit" and "하던 작업입니다" in t["toast"] and "사업계획서 양식 맞추기" in t["toast"], t)
        page.locator("#toast .toast-act").click()  # 「새 작업으로 열기」 — 새 작업이 그 TASK 로
        page.wait_for_function("(w) => state.id && state.id !== w && state.task.job === 'plan_merge' && document.getElementById('panel').dataset.tool === 'Div'", arg=wid, timeout=60000)
        page.wait_for_function(FIRST_DONE, timeout=120000)
        t = page.evaluate(TASK)
        check("「새 작업으로 열기」 — 새 작업이 그 TASK 로 · 첫 분석이 돎", t["id"] != wid and t["task"]["job"] == "plan_merge" and t["task"]["kind"] == "rnd" and t["pane"], t)
        check("앞 작업의 TASK 는 그대로", next(w for w in requests.get(f"{base}/api/works", timeout=10).json() if w["id"] == wid)["task"]["job"] == "plan_fit")

        h = go_home(page)  # 카드에 파일 놓기 — docx 는 안 받는다 · hwpx 는 그 TASK 로(양식 판정이 종류를 정한다)
        DROP = """([b64, name, key]) => { const bin = atob(b64), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
            const dt = new DataTransfer(); dt.items.add(new File([u], name)); const card = document.querySelector(`#taskCards [data-task="${key}"]`), ev = (n) => new DragEvent(n, { bubbles: true, cancelable: true, dataTransfer: dt });
            card.dispatchEvent(ev('dragover')); const marked = card.classList.contains('over') && !document.getElementById('drop').classList.contains('over');
            card.dispatchEvent(ev('drop')); return marked && !card.classList.contains('over'); }"""
        blob = lambda n: base64.b64encode((ROOT / "samples" / n).read_bytes()).decode()
        marked = page.evaluate(DROP, [blob("기술수요조사서.docx"), "기술수요조사서.docx", "plan_to_report"])
        page.wait_for_timeout(400)
        t = page.evaluate(TASK)
        check("카드에 docx 를 놓으면 안 받음(알림 · 시작 화면 그대로) · 올린 동안 카드만 표시", marked and t["id"] is None and "hwp·hwpx" in t["toast"], (marked, t))
        before = {w["id"] for w in requests.get(f"{base}/api/works", timeout=10).json()}
        page.evaluate(DROP, [blob(PLAN), PLAN, "plan_to_report"])
        page.wait_for_function("() => state.id && state.task.job === 'plan_to_report' && document.getElementById('panel').dataset.tool === 'Div' && !!document.querySelector('#paneDiv select[data-task-file=plan]')", timeout=180000)
        t = page.evaluate(TASK)
        slot = page.evaluate("() => document.querySelector('#paneDiv select[data-task-file=plan]').value")
        check("카드에 hwpx 를 놓음 → 새 작업이 그 TASK 로(종류는 양식 판정 = 사업계획서 · 이관의 칸에 듦)", t["id"] not in before and t["task"]["kind"] == "rnd" and t["task"]["file"] == "plan" and slot == t["id"], (t, slot))
        page.screenshot(path=str(OUT / "7_task_drop.png"))
        h = go_home(page)
        cs = page.evaluate(CARDS)
        check("돌아온 시작 화면 — 카드 다섯 장 그대로(올리는 중 표시 없음)", is_home(h) and len(cs) == 5 and not any(c["busy"] for c in cs), (h, cs))
        reopen(page, wid)  # 아래 「좁은 창」 은 작업을 연 채로 본다

        # ---- 8. 좁은 창 — 앱 이름 글은 숨어도 아이콘은 남아 눌린다
        page.set_viewport_size({"width": 1100, "height": 900})
        page.wait_for_timeout(400)
        narrow = page.evaluate("""() => { const a = document.getElementById('homeLink'), r = a.getBoundingClientRect(), s = a.querySelector('span'), f = document.getElementById('fileInfo').getBoundingClientRect();
            return { w: r.width, h: r.height, left: r.left, right: r.right, span: s.getClientRects().length, file: f.left }; }""")
        check("좁은 창(1100px) — 글은 숨고 아이콘만(누를 자리 24px 이상 · 파일 이름과 안 겹침)", narrow["span"] == 0 and narrow["w"] >= 24 and narrow["h"] >= 24 and narrow["left"] >= 0
              and narrow["right"] <= narrow["file"], narrow)
        page.screenshot(path=str(OUT / "8_narrow.png"), clip={"x": 0, "y": 0, "width": 700, "height": 120})
        h = go_home(page)
        check("좁은 창 — 아이콘을 눌러 시작 화면", is_home(h), h)

        bad = [e for e in errors if "favicon" not in e]
        check("콘솔 오류·pageerror 없음", not bad, bad[:5])
        browser.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()

print(f"\n{'실패 ' + str(len(fails)) + '개: ' + ', '.join(fails) if fails else '모두 통과'}")
sys.exit(1 if fails else 0)
