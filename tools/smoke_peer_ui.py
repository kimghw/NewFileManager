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
        page.click("#taskHome")
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
        page.click("#taskHome")
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

        # ---- 3-1. 두 면(② §12 「두 면」) — 탭 줄·편집 도구 줄은 두 문서 위에 한 번 · 창마다 이름 줄 없음 · 줄을 접고 펴도 두 문서의 위끝이 같은 줄
        GEO = """() => { const q = (s) => { const e = document.querySelector(s), b = e.getBoundingClientRect(); return { t: b.top, b: b.bottom, l: b.left, r: b.right, h: b.height, w: b.width, shown: e.getClientRects().length > 0 }; };
            const ws = document.querySelector('.workspace');
            return { ws: q('.workspace'), nav: q('#workspaceNav'), bar: q('#docBar'), viewer: q('#viewer'), sc: q('#scroller'), col: q('#peerCol'), head: q('#peerCol > header'), frame: q('#peerFrame'),
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
            ok = ok and ((g["head"]["shown"] and near(g["head"]["h"], g["nav"]["h"]) and near(g["head"]["t"], g["nav"]["t"])) if nav else not g["head"]["shown"])
            ok = ok and ((g["bar"]["shown"] and near(g["bar"]["l"], min(g["viewer"]["l"], g["col"]["l"])) and near(g["bar"]["r"], max(g["viewer"]["r"], g["col"]["r"]))) if bar else not g["bar"]["shown"])  # 두 문서 위(어느 쪽이 왼쪽이든)
            ok = ok and ((near(g["nav"]["l"], g["viewer"]["l"]) and near(g["head"]["l"], g["col"]["l"])) if nav else True)  # 도구 탭 띠는 고치는 문서 위 · 문서 이름 탭 줄은 옆 문서 위
            if not nav and not bar:
                ok = ok and near(g["sc"]["t"], g["ws"]["t"])  # 두 문서 모두 상단 바 바로 아래
            check(f"두 면 — {name}: 두 문서 위끝·아래끝 같은 줄 · 문서 탭 줄 = 도구 탭 띠 높이 · 편집 도구 줄은 두 문서 위", ok, g)
            page.screenshot(path=str(OUT / f"3_panes_{int(nav)}{int(bar)}.png"))
        g = geo(True, True)
        check("편집 도구 줄 — 두 문서 폭이라 한 줄", g["bar"]["h"] <= 41, g["bar"])
        page.set_viewport_size({"width": 1500, "height": 900})  # 문서 열이 좁아져(두 면 반반 = 490px) 도구 탭 띠가 두 줄로 꺾여도
        g = geo(True, False)
        check("도구 탭 띠가 두 줄로 꺾이면 문서 탭 줄도 그 높이", g["nav"]["h"] >= 50 and near(g["head"]["h"], g["nav"]["h"]) and near(g["sc"]["t"], g["frame"]["t"]), g)
        page.set_viewport_size({"width": 1900, "height": 900})
        geo(True, True)
        page.click("#peerFold")
        g = page.evaluate(GEO)
        check("» 접기 — 28px 띠가 상단 바 아래부터 끝까지 · 편집 도구 줄은 문서 열 위로만", round(g["col"]["w"]) == 28 and near(g["col"]["t"], g["ws"]["t"]) and near(g["col"]["b"], g["ws"]["b"])
              and not g["open"] and near(g["bar"]["r"], g["viewer"]["r"]), g)
        page.click("#peerRail")
        g = page.evaluate(GEO)
        check("띠를 누르면 다시 두 문서 위", g["open"] and near(g["bar"]["l"], min(g["viewer"]["l"], g["col"]["l"])) and near(g["bar"]["r"], max(g["viewer"]["r"], g["col"]["r"])) and near(g["sc"]["t"], g["frame"]["t"]), g)

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
        page.click("#taskHome")
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
        v, p = page.evaluate(RECT, "viewer"), page.evaluate(RECT, "peerCol")
        check("고치는 문서를 바꿔도 자리는 그대로 — 사업계획서(이제 고치는 문서) 왼쪽 · 연차보고서 오른쪽", v["r"] <= p["l"] + 1
              and not page.evaluate("() => document.querySelector('.workspace').classList.contains('peer-left')"), (v, p))
        page.click("#peerClose")
        check("✕ = 끔(기억 off)", page.evaluate(SHOWN) == "" and page.evaluate("() => localStorage.getItem('nfm.peer')") == "off")
        page.evaluate("() => { localStorage.setItem('nfm.peer', 'on'); peerSync(); }")
        check("다시 켬", page.evaluate(SHOWN) == report)
        page.evaluate("() => closeDoc()")
        check("문서를 닫으면 옆 열도 닫힘", page.evaluate("() => document.getElementById('peerCol').hidden && document.getElementById('peerFrame').src === 'about:blank'"))

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
