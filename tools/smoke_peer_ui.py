"""같이 보기(spec_작업 ② §12) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_peer_ui.py <그림·임시 폴더> [--port 18212]

작은 문서 둘(기술수요조사서.hwpx 두 번)을 올려 한 과제의 이관(사업계획서·연차보고서)으로 묶고 연차보고서를 연다:
옆 열에 사업계획서가 읽기 전용으로 뜨는지 · 옆 문서가 GET 밖 요청을 안 보내는지 · 칸 단추·✕·접기·기억 · 문서를 바꾸면 옆 문서도 바뀌는지 · 패널 320px 넘침."""
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
ap.add_argument("--port", type=int, default=18212)
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
errors, fails, writes = [], [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:300] if detail != "" else ""), flush=True)
    if not ok:
        fails.append(name)


def upload(name):
    return requests.post(f"{base}/api/docs?new=1", files={"file": (name, (ROOT / "samples" / name).read_bytes())}, timeout=120).json()["docId"]


def task(wid, file):
    r = requests.put(f"{base}/api/works/{wid}/task", json={"kind": "rnd", "file": file, "job": "plan_to_report", "project": "PEER"}, timeout=10)
    r.raise_for_status()


def open_work(page, wid):
    page.evaluate("(id) => { location.hash = '#w=' + id; }", wid)
    page.reload()
    page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=wid, timeout=120000)


def peek(page):
    """옆 문서 화면(iframe)의 Frame — 문서가 그려질 때까지."""
    page.wait_for_function("() => { const w = document.getElementById('peerFrame').contentWindow; return !!(w && w.document.querySelector('#doc .sheet .para')); }", timeout=120000)
    return next(f for f in page.frames if "peek=" in f.url)


SHOWN = "() => { const c = document.getElementById('peerCol'); return c.getClientRects().length > 0 && !c.hidden ? document.getElementById('peerFrame').dataset.w : ''; }"
BTN = "(k) => { const b = document.querySelector(`#taskFlow [data-task-peer=${k}]`); return b ? { disabled: b.disabled, pressed: b.getAttribute('aria-pressed') } : null; }"
RECT = "(id) => { const r = document.getElementById(id).getBoundingClientRect(); return { l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width) }; }"
ROLE = """() => { const b = document.getElementById('docRole');
  return { mine: { shown: b.getClientRects().length > 0, text: b.textContent, role: b.dataset.role || '' },
           tabs: [...document.querySelectorAll('#peerTabs .tab')].map((t) => [t.dataset.peerDoc, t.dataset.role || '', getComputedStyle(t, '::before').content]) }; }"""

try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    plan, report, third = upload("기술수요조사서.hwpx"), upload("기술수요조사서.hwpx"), upload("기술수요조사서.hwpx")
    task(plan, "plan")
    task(report, "report")
    task(third, "")  # 같은 과제의 칸 없는 문서 — 둘째 면의 문서 이름 탭에만 나온다(② §12 「두 면」)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1900, "height": 900})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("request", lambda r: writes.append(f"{r.method} {r.url}") if r.method != "GET" and "peek=" in (r.frame.url if r.frame else "") else None)
        page.goto(base)
        open_work(page, report)

        # ---- 1. 연차보고서를 열면 옆 열에 사업계획서(기본 켬)
        page.wait_for_function(f"(id) => ({SHOWN})() === id", arg=plan)
        fr = peek(page)
        check("옆 열 = 사업계획서", page.evaluate(SHOWN) == plan and f"peek={plan}" in fr.url, fr.url)
        tabs = page.evaluate("() => [...document.querySelectorAll('#peerTabs .tab')].map((b) => ({ id: b.dataset.peerDoc, on: b.classList.contains('active'), text: b.textContent, shown: b.getClientRects().length > 0 }))")
        check("문서 이름 탭 — 칸 문서(사업계획서)가 먼저·고른 탭, 같은 과제의 다른 문서가 다음", [t["id"] for t in tabs] == [plan, third] and [t["on"] for t in tabs] == [True, False]
              and all(t["shown"] and t["text"] == "기술수요조사서.hwpx" for t in tabs), tabs)
        check("이름 줄 없음 — 머리는 탭 줄(이름은 접힌 띠·aria 용으로만)", not page.is_visible("#peerName") and page.evaluate("() => document.getElementById('peerName').textContent") == "기술수요조사서.hwpx")
        # 목적 문서 표시(② §10 「목적 문서 표시」): 첫째 면 이름 줄 꼬리표 · 둘째 면 탭은 data-role → ::before(탭 글은 이름 그대로)
        role = page.evaluate(ROLE)
        check("목적 문서 표시 — 연차보고서(고치는 문서) = 「목적 문서」 · 사업계획서 탭 = 「원본」 · 칸 없는 문서 탭 = 없음",
              role["mine"] == {"shown": True, "text": "목적 문서", "role": "target"} and role["tabs"] == [[plan, "source", '"원본"'], [third, "", "none"]], role)
        page.screenshot(path=str(OUT / "doc_role.png"), clip={"x": 0, "y": 0, "width": 1900, "height": 130})  # 꼬리표 모양 기록(이름 줄 · 둘째 면 탭)
        v, p, pn = page.evaluate(RECT, "viewer"), page.evaluate(RECT, "peerCol"), page.evaluate(RECT, "panel")
        # 두 면의 좌우 = 칸 차례(② §12 「두 면」 — 사업계획서 왼쪽 · 연차보고서 오른쪽): 연차보고서를 고치는 중이면 옆 문서(사업계획서)가 왼쪽
        check("열 차례 = 사업계획서(옆 문서) · 연차보고서(고치는 문서) · 패널, 문서 ≥ 360", p["r"] <= v["l"] + 1 and v["r"] <= pn["l"] + 1 and v["w"] >= 360 and p["w"] >= 360
              and page.evaluate("() => document.querySelector('.workspace').classList.contains('peer-left')"), (v, p, pn))
        check("옆 화면 = 문서만", fr.evaluate("() => document.body.classList.contains('peek') && ['.topbar', '.workspace-nav', '.doc-bar', '#panel'].every((s) => document.querySelector(s).getClientRects().length === 0)"))
        check("옆 화면 안에 또 옆 열 없음", fr.evaluate("() => document.getElementById('peerCol').hidden && !document.getElementById('peerFrame').getAttribute('src')"))
        check("옆 문단 고칠 수 없음", fr.evaluate("() => [...document.querySelectorAll('#doc .para')].every((p) => p.contentEditable === 'false')"))
        why = fr.evaluate("() => api('/api/docs/x/undo', { method: 'POST' }).then(() => 'sent', (e) => e.message)")
        check("옆 화면 api() 는 GET 밖 요청을 막음", why == "같이 보기는 읽기 전용입니다", why)
        rev = requests.get(f"{base}/api/docs/{plan}", timeout=30).json()["rev"]
        para = fr.locator("#doc .para").first
        before = para.inner_text()
        para.click()
        page.keyboard.type("XYZ")
        page.wait_for_timeout(1500)
        check("옆 문서에 타자해도 글·서버 그대로", para.inner_text() == before and requests.get(f"{base}/api/docs/{plan}", timeout=30).json()["rev"] == rev)

        # ---- 2. 칸 단추(패널 「연구개발과제」)
        page.click("#toolTabTask")
        page.wait_for_selector("#taskFlow [data-task-peer=plan]")
        check("칸 단추 — 사업계획서 눌림 · 연차보고서(지금 문서) 꺼짐", page.evaluate(BTN, "plan") == {"disabled": False, "pressed": "true"} and page.evaluate(BTN, "report")["disabled"],
              (page.evaluate(BTN, "plan"), page.evaluate(BTN, "report")))
        page.screenshot(path=str(OUT / "1_peer.png"))
        rows = page.evaluate("() => { const g = document.querySelector('#taskFlow .dv-flow-files'); return { over: g.scrollWidth - g.clientWidth, tops: [...g.querySelectorAll('label')].map((l) => new Set([...l.children].map((c) => Math.round(c.getBoundingClientRect().top + c.getBoundingClientRect().height / 2))).size) }; }")
        check("칸 줄 = 한 줄에 넷(넘침 없음)", rows["over"] <= 0 and all(n == 1 for n in rows["tops"]), rows)
        page.click("#taskFlow [data-task-peer=plan]")
        check("단추로 닫음 · 기억 off · iframe 비움", page.evaluate(SHOWN) == "" and page.evaluate("() => localStorage.getItem('nfm.peer')") == "off"
              and page.evaluate("() => document.getElementById('peerFrame').src") == "about:blank" and page.evaluate(BTN, "plan")["pressed"] == "false")
        check("닫으면 옆 열 폭 0", page.evaluate(RECT, "viewer")["r"] >= page.evaluate(RECT, "panel")["l"] - 1, (page.evaluate(RECT, "viewer"), page.evaluate(RECT, "panel")))
        open_work(page, report)
        page.wait_for_timeout(800)
        check("새로 고쳐도 꺼진 채", page.evaluate(SHOWN) == "")
        page.click("#toolTabTask")
        page.wait_for_selector("#taskFlow [data-task-peer=plan]")
        page.click("#taskFlow [data-task-peer=plan]")
        fr = peek(page)
        check("단추로 다시 엶 · 기억 on", page.evaluate(SHOWN) == plan and page.evaluate("() => localStorage.getItem('nfm.peer')") == "on" and page.evaluate(BTN, "plan")["pressed"] == "true")

        # ---- 3. 접기 · 폭 · ✕
        page.click("#peerFold")
        check("» 접기 = 28px 띠 + 문서 이름", page.evaluate(RECT, "peerCol")["w"] == 28 and page.inner_text("#peerRail .col-rail-name") == "기술수요조사서.hwpx", page.evaluate(RECT, "peerCol"))
        page.click("#peerRail")
        check("띠 = 펴기", page.evaluate(RECT, "peerCol")["w"] >= 360)
        v, p = page.evaluate(RECT, "viewer"), page.evaluate(RECT, "peerCol")
        check("폭 손잡이 없음 — 두 면 폭은 늘 반반", page.locator("#peerResizer").count() == 0 and abs(v["w"] - p["w"]) <= 1, (v, p))

        # ---- 3-1. 공용 도구 한 줄 + 문서별 파일명 행. 파일명 접기는 탭·편집 접기와 독립(2026-11-12).
        GEO = """() => { const q = (s) => { const e = document.querySelector(s), b = e.getBoundingClientRect(); return { t: b.top, b: b.bottom, l: b.left, r: b.right, h: b.height, w: b.width, shown: e.getClientRects().length > 0 }; };
            const ws = document.querySelector('.workspace');
            return { ws: q('.workspace'), tools: q('#workspaceTools'), names: q('#fileInfo'), nav: q('#workspaceNav'), bar: q('#docBar'), viewer: q('#viewer'), sc: q('#scroller'), col: q('#peerCol'), head: q('#peerCol > header'), frame: q('#peerFrame'),
                     open: ws.classList.contains('peer-open'), pane: ws.classList.contains('pane-peer') ? 'peer' : 'main' }; }"""

        def geo(nav, bar):
            page.evaluate("([n, b]) => { rowFold('nav', !n, false); rowFold('bar', !b, false); }", [nav, bar])
            page.wait_for_timeout(300)
            return page.evaluate(GEO)

        def near(a, b):
            return abs(a - b) < 0.6

        for name, nav, bar in (("둘 다", True, True), ("탭 띠만", True, False), ("편집 줄만", False, True), ("둘 다 접음", False, False)):
            g = geo(nav, bar)
            ok = g["open"] and near(g["sc"]["t"], g["frame"]["t"]) and near(g["sc"]["b"], g["frame"]["b"])
            ok = ok and g["head"]["shown"] and g["names"]["shown"] and near(g["head"]["h"], g["names"]["h"]) and near(g["head"]["t"], g["names"]["t"])
            ok = ok and g["nav"]["shown"] == nav and g["bar"]["shown"] == bar
            ok = ok and near(g["names"]["l"], g["viewer"]["l"]) and near(g["head"]["l"], g["col"]["l"])
            if nav or bar:
                ok = ok and g["tools"]["shown"] and near(g["tools"]["l"], min(g["viewer"]["l"], g["col"]["l"])) and near(g["tools"]["r"], max(g["viewer"]["r"], g["col"]["r"]))
            if nav and bar:
                ok = ok and near(g["nav"]["t"], g["bar"]["t"])
            if not nav and not bar:
                ok = ok and not g["tools"]["shown"] and near(g["names"]["t"], g["ws"]["t"])
            check(f"두 면 — {name}: 공용 도구 한 줄 · 각 문서 위 파일명 · 두 문서 위끝·아래끝 일치", ok, g)
            page.screenshot(path=str(OUT / f"3_panes_{int(nav)}{int(bar)}.png"))
        g = geo(True, True)
        check("편집·도구 탭은 한 줄", g["bar"]["h"] <= 41 and near(g["nav"]["t"], g["bar"]["t"]), g)
        page.click("#fileFold")
        g = page.evaluate(GEO)
        check("파일명 접기는 탭·편집과 독립 — 두 문서 이름만 숨김", not g["names"]["shown"] and not g["head"]["shown"] and g["nav"]["shown"] and g["bar"]["shown"]
              and near(g["sc"]["t"], g["frame"]["t"]) and page.locator("#fileFold").get_attribute("aria-pressed") == "false"
              and page.evaluate("() => localStorage.getItem('nfm.fileFold')") == "1", g)
        page.click("#fileFold")
        page.set_viewport_size({"width": 1500, "height": 900})
        g = geo(True, False)
        check("좁아져도 도구 탭은 한 줄 · 파일명 행 높이 독립 · 두 문서 정렬", g["nav"]["h"] <= 41 and near(g["head"]["h"], g["names"]["h"]) and near(g["sc"]["t"], g["frame"]["t"]), g)
        page.set_viewport_size({"width": 1900, "height": 900})
        geo(True, True)
        page.click("#peerFold")
        g = page.evaluate(GEO)
        check("» 접기 — 28px 띠가 상단 바 아래부터 끝까지 · 공용 도구 행은 문서 열 위로만", round(g["col"]["w"]) == 28 and near(g["col"]["t"], g["ws"]["t"]) and near(g["col"]["b"], g["ws"]["b"])
              and not g["open"] and near(g["tools"]["r"], g["viewer"]["r"]), g)
        page.click("#peerRail")
        g = page.evaluate(GEO)
        check("띠를 누르면 다시 두 문서 위", g["open"] and near(g["tools"]["l"], min(g["viewer"]["l"], g["col"]["l"])) and near(g["tools"]["r"], max(g["viewer"]["r"], g["col"]["r"])) and near(g["sc"]["t"], g["frame"]["t"]), g)

        # ---- 3-2. 두 면은 늘 같은 크기 — 폭 반반 · 둘째 면이 첫째 면의 보기(배율·2쪽 보기·쪽 번호·휠 쪽 넘김)를 따른다. 도구 줄은 하나(두 문서에 함께)
        VIEW = """() => { const f = document.getElementById('peerFrame'), w = f.contentWindow, d = f.contentDocument, r = (e) => e.getBoundingClientRect();
            const s0 = document.querySelector('#doc .sheet'), s1 = d.querySelector('#doc .sheet');
            return { zoom: state.zoom, peerZoom: w.eval('state.zoom'), fit: state.fit, peerFit: w.eval('state.fit'), val: document.getElementById('zoomVal').textContent,
                     two: [document.getElementById('doc').classList.contains('two-up'), d.getElementById('doc').classList.contains('two-up')],
                     hide: [document.getElementById('doc').classList.contains('hide-pages'), d.getElementById('doc').classList.contains('hide-pages')],
                     wheel: [state.wheelFlip, w.eval('state.wheelFlip')],
                     colW: [Math.round(r(document.getElementById('viewer')).width), Math.round(r(document.getElementById('peerCol')).width)],
                     sheetW: [r(s0).width, r(s1).width], sheetX: [r(s0).left - r(document.getElementById('scroller')).left, r(s1).left] }; }"""

        def view():
            page.wait_for_timeout(400)
            return page.evaluate(VIEW)

        def same(v):
            return (v["zoom"] == v["peerZoom"] and abs(v["colW"][0] - v["colW"][1]) <= 1 and abs(v["sheetW"][0] - v["sheetW"][1]) < 1
                    and v["two"][0] == v["two"][1] and v["hide"][0] == v["hide"][1] and v["wheel"][0] == v["wheel"][1])

        v0 = view()
        check("처음 — 폭 반반 · 배율 같음 · 쪽 크기·자리 같음", same(v0) and v0["peerFit"] is None and v0["val"] == f"{round(v0['zoom'] * 100)}%"
              and abs(v0["sheetX"][0] - v0["sheetX"][1]) <= 2, v0)
        page.click("#zoomIn")
        v = view()
        check("확대 — 두 문서가 함께", same(v) and abs(v["zoom"] - (v0["zoom"] + 0.1)) < 0.011, v)
        view0 = page.evaluate("() => localStorage.getItem('nfm.view')")
        page.click("#twoUp")
        v = view()
        check("2쪽 보기 — 두 문서가 함께", same(v) and v["two"] == [True, True], v)
        page.click("#twoUp")
        view()
        check("둘째 면은 보기 기억을 따로 쓰지 않음", page.evaluate("() => localStorage.getItem('nfm.view')") == view0, view0)
        page.evaluate("() => document.getElementById('showPages').click()")
        v = view()
        check("쪽 번호 끔 — 두 문서가 함께", same(v) and v["hide"] == [True, True], v)
        page.evaluate("() => document.getElementById('showPages').click()")
        page.evaluate("() => document.getElementById('wheelFlip').click()")
        v = view()
        check("휠 쪽 넘김 끔 — 두 문서가 함께", same(v) and v["wheel"] == [False, False], v)
        page.evaluate("() => document.getElementById('wheelFlip').click()")
        page.click("#zoomHeight")
        v = view()
        check("높이 맞춤 — 둘째 면도 같은 배율", same(v) and v["fit"] == "height", v)
        page.click("#zoomFit")
        v6 = view()
        check("폭 맞춤 — 두 문서가 함께 처음 크기로", same(v6) and v6["fit"] == "width" and v6["zoom"] == v0["zoom"], v6)
        page.screenshot(path=str(OUT / "3_same_size.png"))
        page.set_viewport_size({"width": 1500, "height": 900})
        v = view()
        check("창을 줄여도 반반 · 같은 배율", same(v) and v["zoom"] < v6["zoom"], v)
        page.evaluate("() => headsDlg('paras', '문단 목록', '')")
        v = view()
        check("2열을 열어도 반반 · 같은 배율 · 두 면 모두 ≥ 360px", same(v) and min(v["colW"]) >= 359, v)
        page.screenshot(path=str(OUT / "3_same_size_heads.png"))
        page.evaluate("() => headsColClose()")
        page.set_viewport_size({"width": 1900, "height": 900})
        v = view()
        check("돌아오면 처음 크기", same(v) and v["zoom"] == v0["zoom"], v)

        # ---- 3-3. 문서 이름 탭 — 누르면 둘째 면의 문서가 바뀐다
        page.click(f"#peerTabs [data-peer-doc='{third}']")
        page.wait_for_function(f"(id) => ({SHOWN})() === id", arg=third)
        page.wait_for_function("(id) => { const w = document.getElementById('peerFrame').contentWindow; return w.location.search.includes(id) && !!w.document.querySelector('#doc .sheet .para'); }", arg=third, timeout=120000)
        on = page.evaluate("() => [...document.querySelectorAll('#peerTabs .tab')].filter((b) => b.classList.contains('active')).map((b) => b.dataset.peerDoc)")
        check("탭 — 셋째 문서로 바뀜 · 고른 탭 하나 · 바뀐 문서도 같은 크기", on == [third] and same(view()), on)
        check("칸 단추 — 사업계획서는 안 눌림(다른 문서가 떠 있음)", page.evaluate(BTN, "plan")["pressed"] == "false", page.evaluate(BTN, "plan"))
        page.click(f"#peerTabs [data-peer-doc='{plan}']")
        page.wait_for_function(f"(id) => ({SHOWN})() === id", arg=plan)
        page.wait_for_function("(id) => { const w = document.getElementById('peerFrame').contentWindow; return w.location.search.includes(id) && !!w.document.querySelector('#doc .sheet .para'); }", arg=plan, timeout=120000)
        fr = peek(page)
        check("탭 — 사업계획서로 돌아옴", f"peek={plan}" in fr.url and page.evaluate(BTN, "plan")["pressed"] == "true", fr.url)

        # ---- 3-4. 도구는 문서마다(② §12 「도구는 문서마다」 — 2026-11-19 사용자 "원본, 목적문서가 따로면 도구도,, 따로 따로 적용하ㄹ수 있게" ·
        #      "task 옆에 문서 넣을 수 있는 곳이 있지.. 구지 꼭풀 네임을 넣을 필요 없어. 그리고 여기 상단에 도구를 문서별로 돌릴 수 있는 기능도" · 이름 줄 "이 행도 … 요청사항과 맞게")
        TOOLDOC = """() => { const q = (sel) => [...document.querySelectorAll(sel)].map((b) => [b.dataset.toolDoc, b.textContent, b.getAttribute('aria-pressed') === 'true', b.getClientRects().length > 0]);
            const bar = document.getElementById('toolDocBar'), src = document.getElementById('toolSource');
            return { bar: bar.getClientRects().length > 0, label: (bar.querySelector('.tool-doc-name') || {}).textContent || '', top: q('#toolDocBar .tool-doc-btn'), panel: q('#toolSource .tool-doc-btn'), text: src.textContent }; }"""
        td = page.evaluate(TOOLDOC)
        want = [[plan, "원본", False, True], [report, "목적", True, True]]
        check("상단 바 「도구」 — 두 문서의 짧은 이름 단추(화면 차례 원본 · 목적) · 눌림 = 고치는 문서(연차보고서)", td["bar"] and td["label"] == "도구" and td["top"] == want, td)
        check("패널 머리 「작업」 옆 — 긴 파일 이름 대신 같은 단추(같은 값)", td["panel"] == want and "기술수요조사서" not in td["text"], td)
        PQ = """() => { const box = document.getElementById('peerQuick'), head = document.querySelector('#peerCol > header'), ro = head.querySelector('.peer-ro'), vis = (e) => e.getClientRects().length > 0;
            return { shown: vis(box), icons: [...box.children].map((b) => [b.dataset.quick, vis(b), b.disabled, b.getAttribute('aria-pressed')]),
                     ro: vis(ro), roCut: vis(ro) && ro.scrollWidth > ro.clientWidth + 1, over: head.scrollWidth > head.clientWidth + 1, w: (() => { const cs = getComputedStyle(head); return Math.round(head.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)); })(),  // 컨테이너 질의가 재는 폭(내용 상자)
                     order: [...head.children].filter(vis).map((e) => e.id || e.className) }; }"""
        page.wait_for_function("() => !document.getElementById('peerQuick').hidden && document.querySelector('#peerQuick #peerDivMarks:not([disabled])') != null", timeout=30000)
        page.wait_for_function("() => { const h = document.getElementById('peerStatus'); return !h.hidden && !!h.querySelector('.ds-chip'); }", timeout=30000)
        pq = page.evaluate(PQ)
        check("둘째 면 이름 줄 — 첫째 면과 같은 차례(탭 · 표시 아이콘 다섯 · 분석 상태) · 「읽기 전용」 은 안 잘림(이 폭이면 감춤 — 680px 이하) · 줄 넘침 없음",
              pq["shown"] and [i[0] for i in pq["icons"]] == ["nameTplMarks", "nameFmtMarks", "nameTblMarks", "nameDivMarks", "nameZones"] and all(i[1] for i in pq["icons"])
              and pq["order"][:3] == ["peerTabs", "peerQuick", "peerStatus"] and not pq["roCut"] and pq["ro"] == (pq["w"] > 680) and not pq["over"], pq)
        page.screenshot(path=str(OUT / "3_4_tool_doc.png"), clip={"x": 0, "y": 0, "width": 1900, "height": 130})
        page.set_viewport_size({"width": 2400, "height": 900})
        page.wait_for_timeout(400)
        pq = page.evaluate(PQ)
        check("넓은 창 — 「읽기 전용」 이 보이고 안 잘림 · 줄 넘침 없음", pq["ro"] and not pq["roCut"] and not pq["over"] and pq["w"] > 680, pq)
        page.screenshot(path=str(OUT / "3_4_tool_doc_wide.png"), clip={"x": 0, "y": 0, "width": 2400, "height": 130})
        page.set_viewport_size({"width": 1900, "height": 900})
        page.wait_for_timeout(400)
        # 둘째 면의 「구분 기준 자리 표시」 를 켬 — 그 면(사업계획서 = 원본)에만 · 기억도 원본의 키에만(첫째 면 · 공통 키는 그대로)
        page.click("#peerDivMarks")
        page.wait_for_function("() => document.getElementById('peerDivMarks').getAttribute('aria-pressed') === 'true'", timeout=30000)
        ls = page.evaluate("() => [localStorage.getItem('nfm.divMarks'), localStorage.getItem('nfm.divMarks@source'), localStorage.getItem('nfm.divMarks@target')]")
        check("둘째 면 아이콘 = 그 문서에만 — 둘째 면 켜짐 · 첫째 면 그대로 꺼짐 · 기억은 「@source」 키에만",
              fr.evaluate("() => divMarksOn()") is True and page.evaluate("() => divMarksOn()") is False and page.get_attribute("#nameDivMarks", "aria-pressed") == "false"
              and ls == [None, "on", None], ls)
        fr.wait_for_function("() => !dv.marks.loading && !!dv.marks.data", timeout=30000)
        check("둘째 면도 구분 기준 자리를 읽는다(GET 만 — 끝의 「GET 밖 요청 0」 이 본다)", fr.evaluate("() => !!dv.marks.data && document.getElementById('doc').classList.contains('dv-marks')"))
        # 두 면에서 보던 곳을 다르게 둔 뒤 「도구」 의 원본을 누름 → 두 면이 문서를 바꾼다(자리 · 보던 곳 · 패널 탭 · 손으로 정한 배율 그대로).
        # 견본은 한 쪽짜리라 200% 로 키워 굴릴 자리를 만든다 — 연차보고서(첫째 면)는 맨 위 · 사업계획서(둘째 면)는 맨 아래
        page.evaluate("() => setZoom(2, null)")
        page.wait_for_function("() => { const w = document.getElementById('peerFrame').contentWindow; return state.zoom === 2 && w.eval('state.zoom') === 2; }", timeout=30000)
        page.wait_for_timeout(600)
        page.evaluate("() => { document.getElementById('scroller').scrollTop = 0; }")
        fr.evaluate("() => { const sc = document.getElementById('scroller'); sc.scrollTop = sc.scrollHeight; }")
        page.wait_for_timeout(400)
        at_main, at_peer, tool0 = page.evaluate("() => viewSpot()"), fr.evaluate("() => viewSpot()"), page.evaluate("() => document.getElementById('panel').dataset.tool")
        check("(준비) 두 면의 보던 곳이 다름", at_main != at_peer, (at_main, at_peer))
        page.click(f"#toolDocBar [data-tool-doc='{plan}']")
        page.wait_for_function(f"([a, b]) => state.id === a && ({SHOWN})() === b", arg=[plan, report], timeout=120000)
        page.wait_for_function("(id) => { const w = document.getElementById('peerFrame').contentWindow; return w.location.search.includes(id) && !!w.document.querySelector('#doc .sheet .para') && w.peekId() === id; }", arg=report, timeout=120000)
        page.wait_for_timeout(1500)
        fr = peek(page)
        v, p = page.evaluate(RECT, "viewer"), page.evaluate(RECT, "peerCol")
        td = page.evaluate(TOOLDOC)
        check("「도구」 원본 → 사업계획서가 고치는 문서 · 연차보고서가 둘째 면 · 자리는 그대로(사업계획서 왼쪽) · 눌림이 원본으로(두 곳 같이)",
              v["r"] <= p["l"] + 1 and td["top"] == [[plan, "원본", True, True], [report, "목적", False, True]] and td["panel"] == td["top"], (v, p, td))
        check("패널에서 보던 탭 그대로", page.evaluate("() => document.getElementById('panel').dataset.tool") == tool0, tool0)
        s1, s2 = page.evaluate("() => viewSpot()"), fr.evaluate("() => viewSpot()")
        same_spot = lambda a, b: bool(a and b) and a.get("id") == b.get("id") and a.get("nth") == b.get("nth") and a.get("page") == b.get("page") and abs(a["f"] - b["f"]) < 0.08
        check("보던 곳 그대로 — 사업계획서는 둘째 면에서 보던 곳 · 연차보고서는 첫째 면에서 보던 곳", same_spot(s1, at_peer) and same_spot(s2, at_main), (at_main, at_peer, s1, s2))
        zz = page.evaluate("() => [state.zoom, state.fit, document.getElementById('peerFrame').contentWindow.eval('state.zoom')]")
        check("손으로 정한 배율(200%) 그대로 — 두 면 모두", zz == [2, None, 2], zz)
        check("표시 값은 문서를 따라감 — 사업계획서(이제 첫째 면) 켜짐 · 연차보고서(둘째 면) 꺼짐",
              page.evaluate("() => divMarksOn()") is True and page.get_attribute("#nameDivMarks", "aria-pressed") == "true" and fr.evaluate("() => divMarksOn()") is False, page.get_attribute("#nameDivMarks", "aria-pressed"))
        page.wait_for_function("() => document.getElementById('peerDivMarks').getAttribute('aria-pressed') === 'false'", timeout=30000)
        page.screenshot(path=str(OUT / "3_4_swapped.png"))
        # 패널 머리의 「목적」 → 다시 바꿈
        page.click(f"#toolSource [data-tool-doc='{report}']")
        page.wait_for_function(f"([a, b]) => state.id === a && ({SHOWN})() === b", arg=[report, plan], timeout=120000)
        page.wait_for_function("(id) => { const w = document.getElementById('peerFrame').contentWindow; return !!w.document.querySelector('#doc .sheet .para') && w.peekId() === id; }", arg=plan, timeout=120000)
        check("패널 머리의 「목적」 → 연차보고서가 다시 고치는 문서(사업계획서는 왼쪽 둘째 면)", page.evaluate("() => document.querySelector('.workspace').classList.contains('peer-left')")
              and page.evaluate(TOOLDOC)["top"] == want)
        # 둘째 면 이름 줄의 분석 상태를 누름 → 도구를 그 문서로 바꾸고 진행표
        page.wait_for_function("() => document.querySelector('#peerStatus button.ds-chip') != null", timeout=30000)
        page.click("#peerStatus button.ds-chip")
        page.wait_for_function(f"([a, b]) => state.id === a && ({SHOWN})() === b", arg=[plan, report], timeout=120000)
        page.wait_for_function("() => { const t = document.getElementById('dsTable'); return !!t && !t.hidden; }", timeout=30000)
        check("둘째 면의 분석 상태를 누름 → 그 문서(사업계획서)가 고치는 문서 · 진행표가 펼쳐짐", page.evaluate("() => state.id") == plan)
        page.keyboard.press("Escape")
        page.click(f"#toolDocBar [data-tool-doc='{report}']")
        page.wait_for_function(f"([a, b]) => state.id === a && ({SHOWN})() === b", arg=[report, plan], timeout=120000)
        page.wait_for_function("(id) => { const w = document.getElementById('peerFrame').contentWindow; return !!w.document.querySelector('#doc .sheet .para') && w.peekId() === id; }", arg=plan, timeout=120000)
        fr = peek(page)
        page.click("#zoomFit")  # 뒤 절은 폭 맞춤에서 본다
        page.wait_for_timeout(400)
        page.evaluate("() => { document.getElementById('scroller').scrollTop = 0; }")
        fr.evaluate("() => { document.getElementById('scroller').scrollTop = 0; }")
        # 둘째 면을 접으면 「도구」 단추는 없다(두 문서가 나란히 보일 때만) · 펴면 다시
        page.click("#peerFold")
        td = page.evaluate(TOOLDOC)
        check("둘째 면을 접으면 「도구」 없음 · 패널 머리는 「목적 문서」(긴 파일 이름 아님)", not td["bar"] and not td["panel"] and td["text"] == "목적 문서", td)
        page.click("#peerRail")
        check("펴면 다시 「도구」", page.evaluate(TOOLDOC)["top"] == want)

        # ---- 4. 옆 문서를 그 자리로(연결 목록이 부르는 peerGo) — 바깥 화면은 안 밀림
        last = fr.evaluate("() => [...document.querySelectorAll('#doc .para')].pop().dataset.id")
        page.evaluate("([w, id]) => peerGo({ id: w }, id)", [plan, last])
        page.wait_for_timeout(1200)
        got = fr.evaluate("(id) => { const r = paraEl(id).getBoundingClientRect(); return { top: r.top, h: innerHeight, flash: paraEl(id).classList.contains('flash') }; }", last)
        check("peerGo — 옆 문서가 그 문단으로", got["flash"] and 0 <= got["top"] <= got["h"], got)
        check("바깥 화면은 그대로", page.evaluate("() => document.scrollingElement.scrollTop === 0 && document.body.scrollTop === 0 && document.querySelector('.workspace').scrollTop === 0"))

        # ---- 5. 문서 비교에서는 안 보이고, 돌아오면 다시
        page.click("#tabCompare")
        check("문서 비교 — 옆 열 없음", page.evaluate(SHOWN) == "")
        page.click("#toolTabTask")
        check("돌아오면 다시", page.evaluate(SHOWN) == plan)

        # ---- 6. 패널 320px 에서 칸 줄 넘침 없음
        page.evaluate("() => document.getElementById('panel').style.setProperty('--panel', '320px')")
        page.wait_for_timeout(300)
        rows = page.evaluate("() => { const g = document.querySelector('#taskFlow .dv-flow-files'), b = document.getElementById('divBox'); return { over: g.scrollWidth - g.clientWidth, box: b.scrollWidth - b.clientWidth, sel: Math.round(g.querySelector('select').getBoundingClientRect().width) }; }")
        check("패널 320px — 칸 줄 가로 넘침 없음", rows["over"] <= 0 and rows["box"] <= 0 and rows["sel"] >= 80, rows)
        page.screenshot(path=str(OUT / "2_panel320.png"))
        page.evaluate("() => document.getElementById('panel').style.removeProperty('--panel')")

        # ---- 7. 사업계획서를 열면 옆 문서 = 연차보고서 · ✕ 로 끔 · 문서를 닫으면 열도 닫힘
        page.evaluate("(id) => openWork(id)", plan)
        page.wait_for_function(f"([a, b]) => state.id === a && ({SHOWN})() === b", arg=[plan, report], timeout=120000)
        fr = peek(page)
        check("문서를 바꾸면 옆 문서도 바뀜", f"peek={report}" in fr.url, fr.url)
        role = page.evaluate(ROLE)
        check("목적 문서 표시 — 사업계획서(고치는 문서) = 「원본 문서」 · 연차보고서 탭 = 「목적」",
              role["mine"] == {"shown": True, "text": "원본 문서", "role": "source"} and role["tabs"][0] == [report, "target", '"목적"'], role)
        v, p = page.evaluate(RECT, "viewer"), page.evaluate(RECT, "peerCol")
        check("고치는 문서를 바꿔도 자리는 그대로 — 사업계획서(이제 고치는 문서) 왼쪽 · 연차보고서 오른쪽", v["r"] <= p["l"] + 1
              and not page.evaluate("() => document.querySelector('.workspace').classList.contains('peer-left')"), (v, p))
        page.click("#peerClose")
        check("✕ = 끔(기억 off)", page.evaluate(SHOWN) == "" and page.evaluate("() => localStorage.getItem('nfm.peer')") == "off")
        page.evaluate("() => { localStorage.setItem('nfm.peer', 'on'); peerSync(); }")
        check("다시 켬", page.evaluate(SHOWN) == report)
        page.evaluate("() => closeDoc()")
        check("문서를 닫으면 옆 열도 닫힘", page.evaluate("() => document.getElementById('peerCol').hidden && document.getElementById('peerFrame').src === 'about:blank'"))
        check("문서를 닫으면 목적 문서 표시도 없음", page.evaluate(ROLE)["mine"]["shown"] is False)

        check("옆 화면이 보낸 GET 밖 요청 0", not writes, writes[:5])
        check("화면 오류 0", not errors, errors[:5])
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
