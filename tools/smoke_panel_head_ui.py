"""패널 머리(spec_작업 ② §10 「패널 머리」) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_panel_head_ui.py <그림·임시 폴더> [--port 18163]

작은 문서 둘(기술수요조사서 hwpx·docx)을 API 로 올려 본다: 패널 머리 첫 줄 = 작업 종류 목록(상단 바에는 없음) · 파일 이름 · ? · » / 둘째 줄 = 지금 보는 도구 이름 + 꼬리표.
패널에 도구 탭 줄은 없다(문서 위 탭 띠와 겹침). 패널에서 「연구개발과제」 를 고르면 그 내용이 열림(탭 띠에 탭은 없다 — 2026-11-12 없앰: 다른 도구를 보다가 돌아오는 길은 둘째 줄 끝 「↩ 작업 내용」 #taskHome)
· 풀면 「검증」 으로 · 탭 띠를 접은 채로도 · 폭(520·430·320·280px) · 접힌 띠 이름 · docx."""
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
    title: r(document.getElementById('toolTitle')), tag: r(document.getElementById('toolTag')), home: r(document.getElementById('taskHome')), pane: r(document.querySelector('#panel .pane:not([hidden])')) }; }"""
NO_TAB = "() => !document.getElementById('tabDiv') && !document.querySelector('#workspaceNav .tab.active, #workspaceNav .tab[aria-selected=true]')"  # 탭 띠에 「연구개발과제」 탭이 없고 활성 탭도 없다
NOLAP = """() => { const t = document.querySelector('.topbar'), r = [...t.children].filter((e) => e.getClientRects().length && !e.classList.contains('spacer')).map((e) => e.getBoundingClientRect());
  return t.scrollWidth <= t.clientWidth + 1 && r.every((x, i) => i === 0 || x.left >= r[i - 1].right - 1); }"""

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
        open_work(page, a)

        # ---- 1. 머리 첫 줄 — 작업 종류 목록(상단 바에는 없음) · 파일 이름 · ? · »
        opts = page.eval_on_selector_all("#panelTask option", "os => os.map(o => [o.value, o.textContent])")
        check("패널 머리에 작업 종류 목록 · 상단 바에는 없음(옛 #taskKind)", page.evaluate(VIS, "panelTask") and opts == [["", "작업 종류 선택"], ["rnd", "연구개발과제"]]
              and page.input_value("#panelTask") == "" and page.locator("#taskKind, .topbar select:not(#docSwitch)").count() == 0, opts)
        check("파일 이름 · 도움말(?) · 접기(»)", page.inner_text("#toolSource") == "기술수요조사서.hwpx" and page.locator("#toolHelp .panel-help").count() == 1
              and "원본을 읽고 저장한 결과" in page.get_attribute("#toolHelp .panel-help", "data-help") and page.evaluate(VIS, "panelFold"))
        for width in (1600, 1280, 1100):
            page.set_viewport_size({"width": width, "height": 800})
            page.wait_for_timeout(200)
            check(f"상단 바 넘침·겹침 없음({width}px)", page.evaluate(NOLAP))
        page.set_viewport_size({"width": 1600, "height": 900})

        # ---- 2. 둘째 줄 — 지금 보는 도구 이름 + 꼬리표 · 패널에 도구 탭 줄은 없다 · 설명 줄도 없다
        check("둘째 줄 = 「검증」 + 「파일·출력」(보임) · 설명 줄 없음", page.evaluate(HEAD) == ["검증", "파일·출력"] and page.evaluate(VIS, "toolTitle") and page.evaluate(VIS, "toolTag")
              and not page.evaluate(VIS, "toolDescription"), page.evaluate(HEAD))
        check("패널에 도구 탭 줄 없음(탭 띠와 겹침)", page.locator("#panelTabs").count() == 0 and page.locator("#panel .tool-heading [role=tab]").count() == 0)
        g0 = page.evaluate(GEO)
        check("머리 높이 78px · 가로 넘침 없음 · 내용이 머리 바로 아래", g0["head"][3] - g0["head"][1] == 78 and g0["over"] <= 0 and g0["pane"][1] == g0["head"][3], g0)
        page.screenshot(path=str(OUT / "1_head.png"))

        # ---- 3. 도구는 문서 위 탭 띠에서 바꾼다 — 둘째 줄이 그 도구 이름으로 · 머리 높이는 그대로
        seen, moved = [], []
        for tool, pane in (("Edits", "paneEdits"), ("Log", "paneLog"), ("Heads", "paneHeads"), ("Tables", "paneTables"), ("Verify", "paneVerify")):
            page.click(f"#tab{tool}")
            page.wait_for_function("(t) => document.getElementById('panel').dataset.tool === t", arg=tool)
            seen.append(page.evaluate(HEAD)[0])
            g = page.evaluate(GEO)
            if not page.evaluate(VIS, pane) or g["head"] != g0["head"] or g["task"] != g0["task"] or g["fold"] != g0["fold"]:
                moved.append([tool, g["head"]])
        check("탭 띠로 도구 바꾸기 — 둘째 줄이 도구 이름 · 머리 높이·첫 줄 자리 그대로", seen == ["고친 문단", "기록", "헤딩 추출", "표", "검증"] and not moved, [seen, moved])

        # ---- 4. 패널에서 작업 = 연구개발과제 → 저장 · 그 내용이 바로 열림(탭 띠에 탭은 안 생긴다 — 2026-11-12)
        check("작업 종류를 고르기 전 — 「↩ 작업 내용」 단추 안 보임", not page.evaluate(VIS, "taskHome"))
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task") and r.request.method == "PUT") as put:
            page.select_option("#panelTask", "rnd")
        page.wait_for_selector("#divBox .dv-task select")
        check("패널에서 「연구개발과제」 를 고름 — PUT 200 · 그 내용이 열림 · 탭 띠에 탭·활성 탭 없음 · 「↩ 작업 내용」 은 감춤", put.value.status == 200 and page.evaluate(TOOL) == "Div" and page.evaluate(VIS, "paneDiv")
              and page.evaluate(NO_TAB) and not page.evaluate(VIS, "taskHome") and page.evaluate(HEAD) == ["연구개발과제", "구분 기준"], page.evaluate(HEAD))
        check("활성 탭이 없어도 Tab 키는 첫 탭(검증)이 받는다", page.evaluate("() => [...document.querySelectorAll('#workspaceNav .tab')].filter((t) => t.tabIndex === 0).map((t) => t.id)") == ["tabVerify"])
        g = page.evaluate(GEO)
        check("연구개발과제 내용 — 머리 높이 78px 그대로", g["head"] == g0["head"] and g["pane"][1] == g["head"][3], g["head"])
        check("작업에 저장", task_of(a)["kind"] == "rnd", task_of(a))
        check("연구개발과제 패널 첫 카드에는 「작업」 칸이 없다(패널 머리의 목록 하나뿐 — 2026-11-12)", page.locator("#divBox .dv-task select[data-task=kind]").count() == 0
              and page.locator("#divBox .dv-task select[data-task=job]").count() == 1)
        page.locator("#panel").screenshot(path=str(OUT / "4_panel_rnd.png"))

        # ---- 5. 탭 띠로 다른 도구를 봐도 작업 목록은 그대로 · 둘째 줄 끝 「↩ 작업 내용」 으로 돌아옴
        page.click("#tabVerify")
        check("탭 띠 「검증」 — 작업 목록은 그대로 「연구개발과제」", page.evaluate(TOOL) == "Verify" and page.input_value("#panelTask") == "rnd" and page.evaluate(HEAD)[0] == "검증")
        g = page.evaluate(GEO)
        check("다른 도구를 볼 때 「↩ 작업 내용」 — 둘째 줄 오른쪽 끝 · 꼬리표와 안 겹침 · 머리 높이 그대로", page.evaluate(VIS, "taskHome") and page.inner_text("#taskHome").strip() == "↩ 작업 내용"
              and g["home"][0] >= g["tag"][2] and g["home"][2] <= g["head"][2] and g["home"][1] >= g["task"][3] and g["head"] == g0["head"] and g["over"] <= 0, g)
        page.locator("#panel .tool-heading").screenshot(path=str(OUT / "5_head_home.png"))
        page.click("#taskHome")
        check("「↩ 작업 내용」 — 그 내용 · 단추는 다시 감춤", page.evaluate(TOOL) == "Div" and page.evaluate(VIS, "paneDiv") and not page.evaluate(VIS, "taskHome") and page.evaluate(NO_TAB))

        # ---- 6. 풀기 — 패널의 목록에서 풀면 「검증」 으로(돌아가는 단추도 없음) · 다시 고르면 다시 열림
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task")):
            page.select_option("#panelTask", "")
        check("패널에서 풀면 — 「검증」 으로 · 「↩ 작업 내용」 없음", not page.evaluate(VIS, "taskHome") and page.evaluate(TOOL) == "Verify" and page.evaluate(HEAD)[0] == "검증"
              and task_of(a)["kind"] == "", page.evaluate(HEAD))
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task")):
            page.select_option("#panelTask", "rnd")
        page.wait_for_selector("#divBox .dv-task select")
        check("패널에서 다시 고르면 — 그 내용이 다시 열림", page.evaluate(TOOL) == "Div" and page.evaluate(VIS, "paneDiv"))
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task")):
            page.select_option("#panelTask", "")
        check("한 번 더 풀어도 같다", page.evaluate(TOOL) == "Verify" and not page.evaluate(VIS, "taskHome") and task_of(a)["kind"] == "")
        check("풀린 문서에서는 showTab('Div') 도 안 열린다", page.evaluate("() => { showTab('Div'); return document.getElementById('panel').dataset.tool; }") == "Verify")

        # ---- 7. 탭 띠를 접은 채로도(상단 바 「탭 ▴」) 패널의 작업 목록으로 연구개발과제 내용을 연다
        page.click("#navFold")
        check("탭 띠 접힘", page.evaluate("() => document.getElementById('workspaceNav').getClientRects().length") == 0)
        with page.expect_response(lambda r: r.url.endswith(f"/api/works/{a}/task")):
            page.select_option("#panelTask", "rnd")
        page.wait_for_selector("#divBox .dv-task select")
        check("탭 띠를 접은 채 패널에서 「연구개발과제」 — 그 내용이 열림 · 둘째 줄이 이름을 보임", page.evaluate(TOOL) == "Div" and page.evaluate(VIS, "paneDiv") and page.evaluate(HEAD)[0] == "연구개발과제")
        page.evaluate("() => showTab('Edits')")  # 탭 띠가 접힌 채 다른 도구로 넘어간 꼴(고친 문단 배지 · 쪽 번호를 눌러 PDF 가 열림 …)
        check("탭 띠를 접은 채 다른 도구 — 「↩ 작업 내용」 이 보임", page.evaluate(TOOL) == "Edits" and page.evaluate(VIS, "taskHome"))
        page.click("#taskHome")
        check("탭 띠를 접은 채로도 「↩ 작업 내용」 으로 돌아옴(옛 미결 — 탭 띠를 접으면 길이 없었다)", page.evaluate(TOOL) == "Div" and page.evaluate(VIS, "paneDiv"))
        page.click("#navFold")
        check("펴도 탭 띠에 「연구개발과제」 탭·활성 탭 없음", page.evaluate(NO_TAB) and page.evaluate(VIS, "tabVerify"))

        # ---- 8. 폭 — 520 · 430 · 320 · 280px: 머리 높이 78px 그대로 · 가로 넘침 없음 · 목록·단추·이름이 머리 안
        for width in (520, 430, 320, 280):
            page.evaluate("(w) => { const c = colSizers.find((x) => x.box === 'panel'); c.w = w; c.apply(); }", width)
            page.wait_for_timeout(300)
            g = page.evaluate(GEO)
            check(f"패널 {width}px — 높이 78px · 넘침 없음 · 머리 안", g["head"][2] - g["head"][0] in (width - 1, width) and g["head"][3] - g["head"][1] == 78 and g["over"] <= 0
                  and g["task"][0] >= g["head"][0] and g["fold"][2] <= g["head"][2] and g["tag"][2] <= g["head"][2] and g["title"][0] >= g["head"][0] and g["pane"][1] == g["head"][3], g)
            page.locator("#panel").screenshot(path=str(OUT / f"8_panel_{width}.png"))
        # 「↩ 작업 내용」 이 보이는 도구(이름이 긴 「고친 문단」·「헤딩 추출」)에서도 좁은 폭에 넘치지 않는다 — 단추는 머리 안, 꼬리표와 안 겹침
        for tool in ("Edits", "Heads"):
            page.click(f"#tab{tool}")
            for width in (320, 280):
                page.evaluate("(w) => { const c = colSizers.find((x) => x.box === 'panel'); c.w = w; c.apply(); }", width)
                page.wait_for_timeout(300)
                g = page.evaluate(GEO)
                check(f"{tool} · 패널 {width}px — 「↩ 작업 내용」 머리 안 · 높이 78px · 넘침 없음", page.evaluate(VIS, "taskHome") and g["head"][3] - g["head"][1] == 78 and g["over"] <= 0
                      and g["home"][2] <= g["head"][2] and g["home"][0] >= g["tag"][2] and g["title"][0] >= g["head"][0] and g["pane"][1] == g["head"][3], g)
            page.locator("#panel").screenshot(path=str(OUT / f"8_panel_280_{tool}.png"))
        page.evaluate("() => { const c = colSizers.find((x) => x.box === 'panel'); c.w = null; c.apply(); }")

        # ---- 9. 문서 비교(전체 폭) — 머리 꼴은 같고 파일 이름 자리는 「여러 문서 …」
        page.click("#tabCompare")
        g = page.evaluate(GEO)
        check("문서 비교 — 둘째 줄 「문서 비교」 · 넘침 없음 · 작업 목록 그대로", page.evaluate(HEAD)[0] == "문서 비교" and g["over"] <= 0 and page.inner_text("#toolSource") == "여러 문서 · 저장된 분석 결과"
              and page.input_value("#panelTask") == "rnd", [page.evaluate(HEAD), g["over"]])
        page.screenshot(path=str(OUT / "9_compare.png"))
        page.click("#taskHome")

        # ---- 10. 접힌 띠 이름 = 지금 보는 도구 이름
        page.click("#panelFold")
        rail = page.inner_text("#panelRail .col-rail-name")
        check("패널을 접으면 띠 이름 = 「연구개발과제」", rail == "연구개발과제" and page.evaluate("() => document.getElementById('panel').classList.contains('folded')"), rail)
        page.click("#panelRail")
        check("띠를 누르면 펴지고 머리 그대로", page.evaluate(VIS, "panelTask") and page.evaluate(TOOL) == "Div")

        # ---- 11. docx — 작업 종류는 문서마다
        open_work(page, b)
        check("docx — 작업 목록은 이 문서의 값(안 고름) · 「↩ 작업 내용」 없음", page.input_value("#panelTask") == "" and not page.evaluate(VIS, "taskHome") and page.evaluate(HEAD)[0] == "검증")
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
