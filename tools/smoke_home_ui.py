"""상단 로고 = 시작 화면으로(spec_작업 ② §7 「시작 화면으로」) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_home_ui.py <그림·임시 폴더> [--port 18179]

- 시작 화면: 로고는 링크(`#homeLink`), 눌러도 그대로(다시 읽지 않음).
- 작업을 연 뒤(표를 고르고 2열 「작성요령 · 표 지침」 을 연 채) 로고 → 시작 화면 · 주소의 `#w=` 걷힘 · 표 손잡이·2열·패널·도구 줄이 남지 않음 · 최근 작업에 그 작업 · 작업은 안 지워짐 ·
  화면을 다시 읽지 않음. 새로 고쳐도 시작 화면, 최근 작업에서 다시 열면 같은 작업.
- 묻는 때: 2열에 저장 안 한 표 지침 글 · 서버에 반영 안 된 수정(「취소」 면 그대로, 「확인」 이면 시작 화면).
- 키보드(초점 + Enter) · Ctrl 누름(새 탭에 시작 화면, 지금 작업은 그대로) · 좁은 창(앱 이름 글이 숨어도 아이콘은 남음).
- TASK 카드(spec_작업 ② §15 — 7-1): 여섯 장(끝에 「문서 일반 편집」 — spec_일반편집 ② §11)·차례·글·로고(그림·바탕색)·줄 수(넓은 창 6 · 860px 3 · 560px 2 · 400px 1) · 준비 중 카드 · 누르면 파일 고르기 → 그 TASK 로 작업 내용 ·
  같은 파일로 하던 작업 이어 열기(같은 TASK·TASK 없음 = 이어 엶 + 「새 작업으로 열기」 · 다른 TASK 를 하던 작업 = 그대로 두고 새 작업 + 「하던 작업 열기」 — ② §15, 2026-11-13) ·
  카드에 파일 놓기(docx 안 받음 · hwpx 는 양식 판정대로)."""
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
        check("TASK 카드 일곱 장 — 할 일 차례(일의 흐름 · 끝에 문서 일반 편집 · 문서 서식 복사)", [c["key"] for c in cards] == ["plan_fit", "plan_merge", "plan_to_report", "report_fit", "report_merge", "doc_edit", "style_copy"], [c["key"] for c in cards])
        check("카드 글 = 문서 / 동작 두 줄", [(c["doc"], c["name"]) for c in cards] == [("사업계획서", "양식 맞추기"), ("사업계획서", "취합"), ("사업계획서 → 연차보고서", "이관"),
                                                                             ("연차보고서", "양식 맞추기"), ("연차보고서", "취합"), ("문서", "일반 편집"), ("문서", "서식 복사")], [(c["doc"], c["name"]) for c in cards])
        check("TASK 마다 로고(그림 있음 · 46px · 바탕 그라데이션)", all(c["sym"] and c["ink"] >= 20 and c["logo"] == 46 and "gradient" in c["bg"] for c in cards), cards)
        check("로고 바탕색 = 문서(사업계획서 둘 같음 · 이관 다름 · 연차보고서 둘 같음 · 일반 편집·서식 복사는 회색 — 보라 아님)", [c["tone"] for c in cards] == ["plan", "plan", "plan-report", "report", "report", "any", "any"]
              and cards[0]["bg"] == cards[1]["bg"] and cards[3]["bg"] == cards[4]["bg"] and cards[5]["bg"] == cards[6]["bg"] and len({cards[0]["bg"], cards[2]["bg"], cards[3]["bg"], cards[5]["bg"]}) == 4
              and "rgb(244, 245, 247)" in cards[5]["bg"], [(c["tone"], c["bg"]) for c in cards])
        check("로고 그림은 TASK 마다 다름", page.evaluate("() => new Set([...document.querySelectorAll('.task-icons symbol')].map((s) => s.innerHTML.replace(/\\s+/g, ''))).size") == 7)
        # 일곱 장이 한 줄 = 왼쪽 열이 1192px 를 넘을 때(landing.css @container home). 2026-11-15 부터 시작 화면 오른쪽에 에이전트 대화창(340~420px — spec_작업에이전트 ② §5)이 있어
        # 창 1500px 에서는 네 장씩 두 줄이다(왼쪽 열이 그 폭 규칙의 기준 — doc_agent_work.css) — 한 줄은 1920px 창에서 본다
        two = page.evaluate("() => { const e = document.getElementById('empty'); return { cols: new Set([...document.querySelectorAll('#taskCards .task-card')].map((c) => Math.round(c.getBoundingClientRect().left))).size, over: e.scrollWidth > e.clientWidth + 1, agent: document.getElementById('homeAgent').getBoundingClientRect().left >= document.querySelector('.home-content').getBoundingClientRect().right - 1 }; }")
        check("창 1500px — 오른쪽에 에이전트 대화창 · TASK 카드는 네 장씩(왼쪽 열 폭에 맞춰) · 가로 넘침 없음", two == {"cols": 4, "over": False, "agent": True}, two)
        page.set_viewport_size({"width": 1920, "height": 1000})
        page.wait_for_timeout(300)
        cards = page.evaluate(CARDS)
        check("넓은 창 — 일곱 장이 한 줄(카드 160px — 본문보다 넓게) · 같은 높이 · 동작 이름이 한 높이(문서 줄이 안 접힘) · 가로 넘침 없음(카드 안 글도)", len({c["top"] for c in cards}) == 1 and len({c["h"] for c in cards}) == 1
              and len(set(page.evaluate("() => [...document.querySelectorAll('#taskCards .task-card-name')].map((e) => Math.round(e.getBoundingClientRect().top))"))) == 1
              and page.evaluate("() => [...document.querySelectorAll('#taskCards .task-card')].every((b) => [...b.querySelectorAll('*')].every((x) => x.getBoundingClientRect().right <= b.getBoundingClientRect().right - 15))")  # 카드 안 여백(16px) 안쪽 — 「… 올려 시작 →」 이 안 넘친다
              and page.evaluate("() => { const e = document.getElementById('empty'); return e.scrollWidth <= e.clientWidth + 1; }"), [(c["top"], c["h"], c["w"]) for c in cards])
        check("준비 중인 TASK 는 「연차보고서 취합」 하나", [c["key"] for c in cards if c["soon"]] == ["report_merge"] and cards[4]["go"] == "준비 중" and cards[0]["go"].startswith("사업계획서 올려 시작"),
              [(c["key"], c["soon"], c["go"]) for c in cards])
        order = page.evaluate("""() => ['.home-intro', '#homeTasks', '.home-capabilities', '#recent'].map((s) => Math.round(document.querySelector(s).getBoundingClientRect().top))""")
        check("자리 — 올리기 묶음 아래 · 기능 소개 줄 위 · 제목 「TASK」", order == sorted(order) and len(set(order)) == 4 and page.evaluate("() => document.getElementById('homeTasksTitle').textContent") == "TASK", order)
        page.screenshot(path=str(OUT / "7_tasks.png"), full_page=True)
        for width, cols in ((1200, 4), (860, 4), (560, 2), (400, 1)):  # 좁은 창 — 카드 줄 수가 준다(가로 넘침 없음): 한 줄 7(시작 화면 폭 1192px 부터) → 4 → 2(760px 이하) → 1(430px 이하)
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

        # 다른 TASK 카드로 같은 파일 — 하던 작업은 그대로 두고 새 작업으로 열어 고른 TASK 를 적는다(② §15 · §19, 2026-11-13: 전에는 TASK 를 안 바꾸고 이어 열며 알림만 —
        # 「양식 맞추기 카드로 올렸는데 TASK 가 이관」). 알림은 뒤따르는 다른 알림(첫 분석)에 밀릴 수 있어 부른 것을 적어 두고 본다
        h = go_home(page)
        page.evaluate("() => { window.__toasts = []; window.__toast0 = toast; toast = (m, e, a) => { window.__toasts.push({ m, act: a || null }); return window.__toast0(m, e, a); }; }")
        with page.expect_file_chooser() as fc:
            page.locator("#taskCards [data-task=plan_merge]").click()
        fc.value.set_files(str(ROOT / "samples" / SMALL))
        page.wait_for_function("""(w) => state.id && state.id !== w && state.task.job === 'plan_merge' && document.getElementById('panel').dataset.tool === 'Div'
            && !!document.querySelector('#paneDiv select[data-task=job]') && window.__toasts.some((x) => x.act && x.act.label === '하던 작업 열기')""", arg=wid, timeout=60000)
        t = page.evaluate(TASK)
        new_id = t["id"]
        note = page.evaluate("() => window.__toasts.filter((x) => x.act && x.act.label === '하던 작업 열기').map((x) => x.m).pop()")
        check("다른 TASK 를 하던 파일 — 새 작업이 고른 TASK 로(작업 내용이 열림)", new_id != wid and t["task"]["job"] == "plan_merge" and t["task"]["kind"] == "rnd" and t["pane"] and t["job"] == "plan_merge", t)
        check("알림 — 하던 작업(TASK 이름)은 그대로 · 새 작업의 TASK · 단추 「하던 작업 열기」", "같은 파일로 하던 작업(TASK 「사업계획서 양식 맞추기」)은 그대로 두고 새 작업으로 열었습니다" in note
              and note.endswith("TASK 「사업계획서 취합」 · 프로젝트 미지정") and t["task"]["project"] == "" and not any("하던 작업입니다" in x["m"] for x in page.evaluate("() => window.__toasts.map((x) => ({ m: x.m }))")), note)
        check("앞 작업의 TASK 는 그대로", next(w for w in requests.get(f"{base}/api/works", timeout=10).json() if w["id"] == wid)["task"]["job"] == "plan_fit")
        how = page.evaluate("""() => { const b = document.querySelector('#toast .toast-act');   // 알림의 단추 — 다른 알림에 밀렸으면 적어 둔 동작을 그대로 부른다
            if (b && b.textContent === '하던 작업 열기' && !document.getElementById('toast').hidden) { b.click(); return 'button'; }
            const a = window.__toasts.map((x) => x.act).filter((x) => x && x.label === '하던 작업 열기').pop(); a.run(); return 'action'; }""")
        page.wait_for_function("(w) => state.id === w && state.task.job === 'plan_fit' && document.getElementById('panel').dataset.tool === 'Div' && !!document.querySelector('#paneDiv select[data-task=job]')", arg=wid, timeout=60000)
        t = page.evaluate(TASK)
        check("「하던 작업 열기」 — 그 작업이 그 TASK 그대로 열림(작업 내용)", t["id"] == wid and t["task"]["job"] == "plan_fit" and t["pane"] and t["job"] == "plan_fit", (how, t))
        page.evaluate("() => { toast = window.__toast0; }")
        first = {}
        for _ in range(600):  # 새 작업이면 첫 분석이 돈다(② §9) — 화면은 하던 작업으로 넘어왔으니 서버에서 본다
            first = requests.get(f"{base}/api/docs/{new_id}/headings", timeout=10).json()
            if first.get("stage2") and first.get("stage3") and (first.get("job") or {}).get("status") != "running":
                break
            time.sleep(.2)
        check("새 작업 — 첫 분석이 돎(헤딩 그래프 · 표 구조)", bool(first.get("stage2") and first.get("stage3")), {k: bool(first.get(k)) for k in ("stage2", "stage3", "job")})
        # 같은 카드로 같은 파일을 다시 — 화면이 고른 TASK 를 함께 보내고(POST /api/docs?job=) 서버가 전에 만든 그 TASK 의 작업을 이어 연다: 새 작업이 또 생기지 않는다(② §15)
        h = go_home(page)
        count = len(requests.get(f"{base}/api/works", timeout=10).json())
        with page.expect_file_chooser() as fc:
            page.locator("#taskCards [data-task=plan_merge]").click()
        with page.expect_response(lambda r: "/api/docs?" in r.url and r.request.method == "POST", timeout=60000) as posted:
            fc.value.set_files(str(ROOT / "samples" / SMALL))
        page.wait_for_function("""(w) => state.id === w && state.task.job === 'plan_merge' && document.getElementById('panel').dataset.tool === 'Div' && !!document.querySelector('#paneDiv select[data-task=job]')
            && !document.getElementById('toast').hidden && document.getElementById('toast').textContent.includes('이어서 엽니다')""", arg=new_id, timeout=60000)
        t = page.evaluate(TASK)
        check("같은 카드로 다시 올림 — ?job= 으로 보내고 그 TASK 의 작업을 이어 엶 · 작업 수 그대로", posted.value.url.endswith("/api/docs?job=plan_merge") and posted.value.json().get("reused") is True
              and posted.value.json()["docId"] == new_id and t["id"] == new_id and len(requests.get(f"{base}/api/works", timeout=10).json()) == count and "이어서 엽니다" in t["toast"], (posted.value.url, t))
        h = go_home(page)
        with page.expect_file_chooser() as fc:  # 처음의 카드로도 — 그 TASK(양식 맞추기)의 작업(wid)이 열린다(가장 최근 작업 = 취합 작업이 아니라)
            page.locator("#taskCards [data-task=plan_fit]").click()
        fc.value.set_files(str(ROOT / "samples" / SMALL))
        page.wait_for_function("(w) => state.id === w && state.task.job === 'plan_fit' && document.getElementById('panel').dataset.tool === 'Div'", arg=wid, timeout=60000)
        check("다른 카드로 다시 올림 — 그 TASK 의 작업이 열림(가장 최근 작업이 아니라) · 작업 수 그대로", page.evaluate("() => state.id") == wid and len(requests.get(f"{base}/api/works", timeout=10).json()) == count)

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
        check("돌아온 시작 화면 — 카드 일곱 장 그대로(올리는 중 표시 없음)", is_home(h) and len(cs) == 7 and not any(c["busy"] for c in cs), (h, cs))

        # ---- 7-2. 최근 작업 줄 = 무슨 일의 어느 작업(spec_작업 ② §7) — TASK 로고·이름 · 작업 이름(프로젝트 이름 — 2026-11-12 「과제」→「프로젝트」, ② §17) · 역할 · TASK 없는 작업은 파일 이름 + 「TASK 없음」
        drop_id = t["id"]
        r = requests.put(f"{base}/api/works/{drop_id}/task", json={**t["task"], "project": "시험 과제"}, timeout=10)  # 이관 작업에 과제 이름
        check("과제 이름 적음(PUT …/task)", r.ok and r.json()["task"]["project"] == "시험 과제", r.text[:200])
        with (ROOT / "samples" / "기술수요조사서.docx").open("rb") as f:  # TASK 없는 작업 하나(국가R&D 양식이 아니라 짐작도 없음)
            plain = requests.post(f"{base}/api/docs?new=1", files={"file": ("기술수요조사서.docx", f)}, timeout=120).json()["docId"]
        page.evaluate("() => loadWorks()")
        page.wait_for_function("(p) => !!document.querySelector(`#workList .recent-work-open[title$='작업 ${p}']`)", arg=plain, timeout=30000)
        ROWS = """() => [...document.querySelectorAll('#workList .recent-work-open')].map((b) => { const q = (s) => b.querySelector(s), tx = (s) => (q(s) || {}).textContent || '', lg = q('.task-logo'), u = lg && lg.querySelector('use');
            return { id: b.title.split('작업 ').pop(), title: tx('.recent-work-title'), dim: !!q('.recent-work-title.none'), chip: tx('.recent-task'), tone: (q('.recent-task') || {}).dataset ? q('.recent-task').dataset.doc || '' : '',
                     role: tx('.recent-work-role'), name: tx('.recent-work-name'), logo: lg ? lg.dataset.doc : null, href: u ? u.getAttribute('href') : null, sym: !!(u && document.querySelector(u.getAttribute('href'))),
                     size: lg ? Math.round(lg.getBoundingClientRect().width) : 0, file: !!q('.recent-file-icon'), label: b.getAttribute('aria-label'), tags: q('.recent-work-foot .recent-work-status') ? 1 : 0,
                     pads: [...b.querySelectorAll('.none')].map((x) => parseFloat(getComputedStyle(x).paddingLeft)), chipH: Math.round(q('.recent-task').getBoundingClientRect().height) }; })"""
        rows = {x["id"]: x for x in page.evaluate(ROWS)}
        check("최근 작업 네 줄(이어 연 작업 · 새 작업 둘 · TASK 없는 작업)", set(rows) == {wid, drop_id, plain, t_merge} if (t_merge := next((w["id"] for w in requests.get(f"{base}/api/works", timeout=10).json() if (w.get("task") or {}).get("job") == "plan_merge"), None)) else False, list(rows))
        a, m, d, p = rows.get(wid, {}), rows.get(t_merge, {}), rows.get(drop_id, {}), rows.get(plain, {})
        check("TASK 있는 줄 — 그 TASK 로고(그림 있음 · 41px · 바탕 = 문서) + TASK 이름 표지(같은 문서 색)",
              [(x.get("href"), x.get("logo"), x.get("tone"), x.get("chip")) for x in (a, m, d)] == [("#taskIcon-plan_fit", "plan", "plan", "사업계획서 양식 맞추기"), ("#taskIcon-plan_merge", "plan", "plan", "사업계획서 취합"),
                                                                                  ("#taskIcon-plan_to_report", "plan-report", "plan-report", "사업계획서 → 연차보고서 이관")]
              and all(x.get("sym") and x.get("size") == 41 and not x.get("file") for x in (a, m, d)), (a, m, d))
        check("작업 이름 = 프로젝트 이름 — 없으면 흐린 「프로젝트 이름 없음」", d.get("title") == "시험 과제" and not d.get("dim") and a.get("title") == "프로젝트 이름 없음" and a.get("dim"), (a, d))
        check("둘째 줄 = 이 문서의 역할 + 파일 이름(취합의 사업계획서는 「취합본」)", (a.get("role"), m.get("role"), d.get("role")) == ("사업계획서", "취합본", "사업계획서")
              and a.get("name") == SMALL and d.get("name", "").startswith(PLAN.rsplit(".", 1)[0]), (a, m, d))
        check("TASK 없는 줄 — 파일 형식 그림 · 첫 줄 = 파일 이름 · 「TASK 없음」 · 역할 줄 없음", p.get("file") and p.get("logo") is None and p.get("title") == "기술수요조사서.docx" and p.get("chip") == "TASK 없음"
              and p.get("role") == "" and p.get("name") == "", p)
        check("흐린 표시(.none — 「TASK 없음」 · 「프로젝트 이름 없음」 · 「검증 전」)에 빈 목록 줄의 큰 여백이 안 붙음 · 표지 높이 24px 이하",
              all(v <= 8 for x in (a, m, d, p) for v in x.get("pads", [99])) and all(x.get("chipH", 99) <= 24 for x in (a, m, d, p)), [(x.get("pads"), x.get("chipH")) for x in (a, m, d, p)])
        check("읽는 이름(aria-label)에 프로젝트 · TASK · 라운드 · 역할", d.get("label", "").startswith("프로젝트 「시험 과제」 · TASK 「사업계획서 → 연차보고서 이관」 · Round 1 · 사업계획서")
              and a.get("label", "").startswith("프로젝트 미지정 · TASK 「사업계획서 양식 맞추기」") and "TASK 없음" in p.get("label", ""), (d.get("label"), a.get("label"), p.get("label")))
        page.locator("#recent").scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "7_recent.png"))
        page.locator("#recentAll").click()
        page.wait_for_selector("#worksDlg[open] #workListDlg .work-task")
        dlg = page.evaluate("""() => [...document.querySelectorAll('#workListDlg .work-open')].map((b) => ({ name: b.querySelector('.work-name').textContent, task: b.querySelector('.work-task').textContent,
            tagH: Math.max(...[...b.querySelectorAll('.vtag, .recent-task')].map((x) => Math.round(x.getBoundingClientRect().height))) }))""")
        check("작업 목록 창에도 프로젝트 · TASK · 라운드 · 역할 줄", any(x["task"] == "프로젝트 「시험 과제」사업계획서 → 연차보고서 이관Round 1 · 사업계획서" for x in dlg) and any(x["task"] == "TASK 없음" for x in dlg)
              and any(x["task"] == "프로젝트 미지정사업계획서 취합Round 1 · 취합본" for x in dlg), dlg)
        check("작업 목록 창 — 표지(검증 · TASK) 높이 24px 이하(빈 목록 줄의 여백이 안 붙음)", all(x["tagH"] <= 24 for x in dlg), [x["tagH"] for x in dlg])
        page.screenshot(path=str(OUT / "7_recent_dialog.png"))
        page.evaluate("() => document.getElementById('worksDlg').close()")
        for width in (560, 400):  # 좁은 창 — 줄이 넘치지 않음(표지는 다음 줄로)
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(250)
            fit = page.evaluate("() => { const ul = document.getElementById('workList'), r = ul.getBoundingClientRect(); return [...ul.querySelectorAll('.recent-work-open *')].every((x) => { const b = x.getBoundingClientRect(); return !b.width || (b.left >= r.left - 1 && b.right <= r.right + 1); }); }")
            check(f"창 {width}px — 최근 작업 줄이 넘치지 않음", fit)
            page.locator("#recent").scroll_into_view_if_needed()
            page.screenshot(path=str(OUT / f"7_recent_{width}.png"))
        page.set_viewport_size({"width": 1500, "height": 1000})
        page.wait_for_timeout(250)

        # ---- 7-3. TASK 하나가 한 줄(spec_작업 ② §7, 2026-11-13 사용자 "동일한 프로젝트에서 동일한 task 인데 왜 동일한게 있냐") — 같은 프로젝트 · 같은 TASK 의 문서들 = 한 줄,
        #      누르면 마지막에 고친 문서 · 나머지는 「다른 문서」 단추 · 최신 라운드만 · 제목 옆 숫자 = 줄 수 · 문서 수. 프로젝트 없는 작업(wid · t_merge)은 위 7-2 처럼 낱개.
        def new_work(task):
            with (ROOT / "samples" / SMALL).open("rb") as f:
                nid = requests.post(f"{base}/api/docs?new=1", files={"file": (SMALL, f)}, timeout=120).json()["docId"]
            r = requests.put(f"{base}/api/works/{nid}/task", json=task, timeout=10)
            check(f"같은 프로젝트 · TASK 에 문서 하나 더(PUT …/task — Round {task.get('round', 1)})", r.ok, r.text[:200])
            return nid
        GROUP = """(id) => { const li = [...document.querySelectorAll('#workList > li.recent-work')].filter((x) => (x.dataset.works || '').split(' ').includes(id));
            if (li.length !== 1) return { n: li.length }; const x = li[0], b = x.querySelector('.recent-work-open'), d = x.querySelector('.recent-work-docs'), ul = document.getElementById('workList').getBoundingClientRect();
            return { n: 1, works: x.dataset.works.split(' '), group: x.classList.contains('recent-group'), flat: getComputedStyle(x).display !== 'flex', opens: b.title.split('작업 ').pop(),
                     meta: x.querySelector('.recent-work-meta').textContent, round: (x.querySelector('.recent-work-round') || {}).textContent || '', label: b.getAttribute('aria-label'),
                     docs: [...x.querySelectorAll('.recent-work-doc')].map((e) => e.title.split('작업 ').pop()), below: !d || d.getBoundingClientRect().top >= b.getBoundingClientRect().bottom - 1,
                     fit: [...x.querySelectorAll('*')].every((e) => { const r = e.getBoundingClientRect(); return !r.width || (r.left >= ul.left - 1 && r.right <= ul.right + 1); }),
                     count: document.getElementById('recentCount').textContent }; }"""
        ROWCOUNT = "async () => { const l = await api('/api/works'); return [recentRows(l).length, l.length]; }"
        same = {"kind": "rnd", "file": "report", "job": "plan_to_report", "project": "시험 과제"}  # drop_id(사업계획서)와 같은 프로젝트 · TASK
        g2 = new_work(same)
        page.evaluate("() => loadWorks()")
        page.wait_for_function("(id) => !!document.querySelector(`#workList > li.recent-work[data-works~='${id}']`)", arg=g2, timeout=30000)
        ws = {w["id"]: w for w in requests.get(f"{base}/api/works", timeout=10).json()}
        last, other = sorted([drop_id, g2], key=lambda i: ws[i].get("updated") or 0, reverse=True)
        g, (nrows, ndocs) = page.evaluate(GROUP, g2), page.evaluate(ROWCOUNT)
        check("같은 프로젝트 · 같은 TASK 문서 둘 = 한 줄(li.recent-group · data-works 에 둘 다 · 다른 줄에 안 나옴)", g.get("n") == 1 and g.get("group") and g.get("flat") and set(g.get("works", [])) == {drop_id, g2}, g)
        check("그 줄을 누르면 마지막에 고친 문서 · 나머지는 줄 아래 「다른 문서」 단추", g.get("opens") == last and g.get("docs") == [other] and g.get("below"), (g, last, other))
        check("묶음 줄 셋째 줄 「문서 2개」 · Round 1 표지는 안 보임 · 읽는 이름에 「문서 2개 중」", g.get("meta", "").startswith("문서 2개") and g.get("round") == "" and "문서 2개 중" in g.get("label", ""), g)
        check("제목 옆 숫자 = 줄 수 · 문서 수(다를 때)", nrows < ndocs and g.get("count") == f"전체 {nrows}개 · 문서 {ndocs}개", (g.get("count"), nrows, ndocs))
        page.locator("#recent").scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "7_recent_group.png"))
        page.set_viewport_size({"width": 400, "height": 900})
        page.wait_for_timeout(250)
        g = page.evaluate(GROUP, g2)
        check("창 400px — 묶음 줄(「다른 문서」 줄 포함)이 넘치지 않고 단추 줄은 아래", g.get("fit") and g.get("below"), g)
        page.locator("#recent").scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "7_recent_group_400.png"))
        page.set_viewport_size({"width": 1500, "height": 1000})
        page.wait_for_timeout(250)
        page.locator(f"#workList .recent-work-doc[title$='작업 {other}']").click()
        page.wait_for_function("(w) => state.id === w && document.querySelector('#doc .sheet .para') != null", arg=other, timeout=60000)
        check("「다른 문서」 단추 → 그 문서가 열림", page.evaluate("() => state.id") == other)
        page.wait_for_timeout(300)
        h = go_home(page)
        check("다시 시작 화면", is_home(h), h)
        g3 = new_work({**same, "round": 2})  # 새 라운드 — 최근 작업에는 최신 라운드 문서만
        page.evaluate("() => loadWorks()")
        page.wait_for_function("(id) => !!document.querySelector(`#workList > li.recent-work[data-works~='${id}']`)", arg=g3, timeout=30000)
        g = page.evaluate(GROUP, g3)
        hidden = page.evaluate("(ids) => ids.filter((id) => !!document.querySelector(`#workList > li.recent-work[data-works~='${id}']`))", [drop_id, g2])
        nlist = page.evaluate("() => document.querySelectorAll('#workListDlg .work-open').length")
        check("새 라운드 — 최신 라운드 문서만 한 줄(「Round 2」 표지) · 이전 라운드 문서는 최근 작업에 없고 작업 목록 창에는 그대로",
              g.get("n") == 1 and g.get("works") == [g3] and g.get("round") == "Round 2" and not g.get("group") and not hidden
              and nlist == len(requests.get(f"{base}/api/works", timeout=10).json()), (g, hidden, nlist))
        page.locator("#recent").scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "7_recent_round2.png"))

        # ---- 7-4. 최근 작업 줄 끝 × = 그 줄의 문서 지우기(spec_작업 ② §7 「작업 지우기」, 2026-11-16 사용자 "작업 삭제 기능이 없네.") — 줄 아래 확인 줄(창 없음) · 지우는 것은 그 줄에 든 문서(TASK 의 최신 라운드)
        DEL = """(id) => { const li = document.querySelector(`#workList > li.recent-work[data-works~='${id}']`); if (!li) return null;
            const x = li.querySelector('.recent-work-del'), r = x.getBoundingClientRect(), e = li.querySelector('.recent-work-end').getBoundingClientRect(), o = li.querySelector('.recent-work-open').getBoundingClientRect(),
              ul = document.getElementById('workList').getBoundingClientRect(), d = li.querySelector('.recent-work-drop');
            return { n: document.querySelectorAll('#workList .recent-work-del').length, rows: document.querySelectorAll('#workList > li.recent-work').length, expanded: x.getAttribute('aria-expanded'), label: x.getAttribute('aria-label'),
                     inRow: r.top >= o.top && r.bottom <= o.bottom && r.right <= ul.right + 1, clear: r.left >= e.right - 1, size: Math.round(r.width),
                     text: d ? d.querySelector('.work-drop-text').textContent : '', names: d ? [...d.querySelectorAll('.work-drop-names > li')].map((n) => n.textContent) : [],
                     focus: document.activeElement.dataset.recentDrop || (document.activeElement.classList.contains('recent-work-del') ? 'x' : ''),
                     fit: !d || [...d.querySelectorAll('*'), d].every((n) => { const b = n.getBoundingClientRect(); return !b.width || (b.left >= ul.left - 1 && b.right <= ul.right + 1); }) }; }"""
        ids_now = lambda: {w["id"] for w in requests.get(f"{base}/api/works", timeout=10).json()}
        x_of = lambda wid_: page.locator(f"#workList > li.recent-work[data-works~='{wid_}'] .recent-work-del")
        asked = len(dialogs)
        g3_name = next(w["name"] for w in requests.get(f"{base}/api/works", timeout=10).json() if w["id"] == g3)  # 보이는 이름(목적 문서는 프로젝트 꼬리가 붙는다 — ② §10) — 줄·확인 줄·알림이 같은 이름을 쓴다
        d = page.evaluate(DEL, g3)
        check("최근 작업 줄마다 × (줄 안 오른쪽 끝 · 「이어서 열기」 와 안 겹침 · 누를 자리 24px 이상 · 읽는 이름)", d["n"] == d["rows"] and d["inRow"] and d["clear"] and d["size"] >= 24
              and d["expanded"] == "false" and d["label"].endswith("지우기"), d)
        x_of(g3).click()
        d = page.evaluate(DEL, g3)
        check("× → 그 줄 아래 확인 줄(문서 이름 · 되살릴 수 없음 · 이전 라운드는 남음) · 포커스는 취소 · 브라우저 창 없음 · 아직 안 지움",
              f"문서 「{g3_name}」을(를) 지울까요?" in d["text"] and "되살릴 수 없습니다" in d["text"] and "이전 라운드 1개는 남습니다" in d["text"] and d["focus"] == "cancel" and d["expanded"] == "true"
              and len(dialogs) == asked and g3 in ids_now(), d)
        page.locator("#recent").scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "7_recent_drop.png"))
        page.keyboard.press("Escape")
        d = page.evaluate(DEL, g3)
        check("Esc — 확인 줄 닫힘 · 포커스는 그 × 로 · 문서 그대로", d["text"] == "" and d["focus"] == "x" and g3 in ids_now(), d)
        x_of(g3).click()
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{g3}") and r.request.method == "DELETE", timeout=30000) as dropped:
            page.locator('#workList [data-recent-drop="ok"]').click()
        page.wait_for_function("(id) => !!document.querySelector(`#workList > li.recent-work[data-works~='${id}']`) && !recentDrop", arg=g2, timeout=30000)  # Round 2 가 없어져 Round 1 의 두 문서가 다시 한 줄로
        g = page.evaluate(GROUP, g2)
        check("지우기 — DELETE /api/works/{id} · 그 줄의 문서만 없어지고 이전 라운드는 남아 다시 최근 작업 줄로 · 알림", dropped.value.status == 200 and g3 not in ids_now() and {drop_id, g2} <= ids_now()
              and set(g.get("works", [])) == {drop_id, g2} and f"문서 「{g3_name}」을(를) 지웠습니다" in page.locator("#toast").text_content(), (page.locator("#toast").text_content(), g))
        x_of(g2).click()
        d = page.evaluate(DEL, g2)
        check("묶음 줄의 × — 「프로젝트 · TASK · Round 의 문서 N개」 + 문서 이름 목록", "프로젝트 「시험 과제」 · TASK 「사업계획서 → 연차보고서 이관」 · Round 1 의 문서 2개를 지울까요?" in d["text"]
              and len(d["names"]) == 2 and "이전 라운드" not in d["text"] and d["fit"], d)
        page.set_viewport_size({"width": 400, "height": 900})
        page.wait_for_timeout(250)
        d = page.evaluate(DEL, g2)
        check("창 400px — × 와 확인 줄이 넘치지 않음", d["inRow"] and d["fit"] and d["size"] >= 24, d)
        page.locator("#recent").scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "7_recent_drop_400.png"))
        page.set_viewport_size({"width": 1500, "height": 1000})
        page.wait_for_timeout(250)
        page.locator('#workList [data-recent-drop="ok"]').click()
        page.wait_for_function("(id) => !document.querySelector(`#workList > li.recent-work[data-works~='${id}']`) && !recentDrop", arg=g2, timeout=30000)
        check("묶음 줄 지우기 — 그 줄의 문서를 다 지움 · 다른 작업은 그대로 · 알림 · 브라우저 창 없음", not ({drop_id, g2} & ids_now()) and {wid, plain} <= ids_now()
              and "의 문서 2개를 지웠습니다" in page.locator("#toast").text_content() and len(dialogs) == asked and is_home(page.evaluate(HOME)), page.locator("#toast").text_content())
        reopen(page, wid)  # 아래 「좁은 창」 은 작업을 연 채로 본다

        # ---- 8. 좁은 창 — 앱 이름 글은 숨어도 아이콘은 남아 눌린다
        page.set_viewport_size({"width": 1100, "height": 900})
        page.wait_for_timeout(400)
        # 파일 이름은 2026-11-12 상단 바에서 문서 위 파일명 줄(#fileInfo.document-name-row)로 옮겼다(spec_작업 ② §17) — 상단 바에서 로고 오른쪽은 줄 조절 묶음(#barCtl)
        narrow = page.evaluate("""() => { const a = document.getElementById('homeLink'), r = a.getBoundingClientRect(), s = a.querySelector('span'), n = document.getElementById('barCtl').getBoundingClientRect();
            return { w: r.width, h: r.height, left: r.left, right: r.right, span: s.getClientRects().length, next: n.left, nextW: n.width }; }""")
        check("좁은 창(1100px) — 글은 숨고 아이콘만(누를 자리 24px 이상 · 옆 줄 조절 단추와 안 겹침)", narrow["span"] == 0 and narrow["w"] >= 24 and narrow["h"] >= 24 and narrow["left"] >= 0
              and narrow["nextW"] > 0 and narrow["right"] <= narrow["next"], narrow)
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
