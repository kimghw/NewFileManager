"""표 메뉴(spec_헤딩_추출 ② §16 — 표 모서리 손잡이 · 빈 필드 제거 · 엑셀식 보기 · 서식으로 변환) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_table_menu_ui.py <그림·임시 폴더> [--port 18176]

기술수요조사서.hwpx 를 새 작업으로 열고 → 도는 중에 다시 연 작업은 헤딩 탭을 안 열어도 끝날 때까지 읽음 → 표 칸을 누르면 고른 표 테두리 + 모서리 손잡이(아이콘 2개 —
표 메뉴 · 그 아래 작성요령 · 표 지침) → 둘째 아이콘 → 「작성요령 · 표 지침」 열 → 손잡이 → 표 메뉴 → 「빈 필드 제거하기」(찾은 줄 · 문서 미리보기 · 지우기 · 실행 취소) → 「엑셀식 보기」 → 「서식으로 변환하기」(표 양식 목록 · 바로 입히기 · 최근 쓴 표 양식) →
「이 표를 표 양식으로 지정」 → 손잡이 다시 누르면 닫힘 → 「프로젝트 구성에 맞추기…」(spec_테이블매니저 ② §9 「표 하나만 프로젝트 구성에 맞추기」 — 연구개발과제 문서에서만 항목 ·
지원 양식이 아니면 까닭 글 · 일반 문서에는 항목 없음 · 연구개발계획서 양식에서 자리 목록 「지금 n개 → 프로젝트 구성 m개」 · 자리가 없는 표 · 프로젝트 구성 값이 없을 때 ·
고른 자리만의 변경 계획(문서 옆 목록이 그 표의 자리만) → 패널의 「반영」 → 실행 취소) → docx 는 hwpx 전용 항목이 꺼짐(「프로젝트 구성에 맞추기…」 는 항목 없음) · 콘솔 오류.
상단 바 LLM 단계 동그라미·「작업에 자동 저장」 글은 2026-11-11 없앰 — 없는지만 본다."""
import argparse
import os
import re
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
ap.add_argument("--port", type=int, default=18176)
args = ap.parse_args()
OUT = Path(args.out).resolve()
SMALL, DOCX = "기술수요조사서.hwpx", "기술수요조사서.docx"
FORM = ROOT / "samples" / "연구개발계획서_양식.hwpx"   # 「프로젝트 구성에 맞추기…」 — 구분 기준 자리가 든 표가 있는 지원 양식
VALUES = {"stages": [2, 3], "orgs": {"lead": "인텍", "joint": ["가나대", "다라연"], "nonprofit": [False, True, False]}}   # 기관 3 · 차년도 5

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
errors, fails = [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:400] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def open_sample(page, name, timeout=240000):
    page.evaluate("() => { const s = document.getElementById('sampleSection'); s.hidden = false; s.open = true; }")
    page.evaluate("(n) => document.querySelector(`.sample[aria-label=\"예제 ${n} 열기\"]`).click()", name)
    page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=timeout)


def menu(page):
    """열린 표 메뉴의 항목 [{text, disabled, cls}] — 닫혀 있으면 None."""
    return page.evaluate("""() => { const m = document.querySelector('.ctx-menu'); if (!m || m.hidden || m.dataset.by !== 'tmn') return null;
        return [...m.querySelectorAll('button')].map((b) => ({text: b.textContent, disabled: b.disabled, cls: b.className})); }""")


def item(page, text):
    return page.locator(f".ctx-menu[data-by='tmn'] button:has-text('{text}')").first


def corner(page, tid):
    """표 칸을 눌러 고른 표로 만들고 손잡이를 누른다."""
    page.locator(f"#doc table.tbl[data-tbl='{tid}'] td .para").first.click()
    page.wait_for_selector(f".tbl-corner[data-for='{tid}']")
    page.locator(".tbl-corner").click()
    page.wait_for_selector(".ctx-menu[data-by='tmn']:not([hidden])")


def corner_far(page, tid):
    """긴 문서의 먼 표 — 그 표로 굴린 뒤 손잡이를 누른다(table_kv 검사의 corner 와 같게)."""
    page.locator(f"#doc table.tbl[data-tbl='{tid}'] td .para").first.scroll_into_view_if_needed()
    page.wait_for_timeout(1500)
    corner(page, tid)


FIRST_DONE = "() => typeof heads !== 'undefined' && heads.view && heads.view.stage2 && heads.view.stage3 && !(heads.view.job && heads.view.job.status === 'running')"

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
        page.on("dialog", lambda d: d.accept())
        page.goto(base)
        page.wait_for_selector("#drop")
        check("상단 바에 LLM 단계 동그라미 없음(2026-11-11 제거)", page.evaluate("() => !document.getElementById('llmStages')"))

        # ---- 1. LLM 작업이 도는 중에 문서를 열면(새로 고침) — 헤딩 탭을 안 열어도 끝날 때까지 요약을 읽는다(app.js headsPeek → headsPoll). 요약 응답 앞 2번에만 도는 작업을 얹는다
        open_sample(page, SMALL)
        page.wait_for_function(FIRST_DONE, timeout=120000)
        page.wait_for_timeout(500)
        wid, seen = page.evaluate("() => state.id"), {"n": 0}

        def fake_running(route):
            seen["n"] += 1
            resp = route.fetch()
            body = resp.json()
            if seen["n"] <= 2:
                body["job"] = {"stage": 2, "llm": True, "first": False, "status": "running", "error": None, "run": None, "rev": body.get("rev"), "started": time.time() - 30, "ended": None,
                               "steps": [{"name": "헤딩 그래프 — LLM", "status": "running", "msg": "", "seconds": 0}]}
            route.fulfill(response=resp, json=body)
        page.route("**/api/docs/*/headings", fake_running)
        page.evaluate("(w) => { location.hash = `w=${w}`; }", wid)
        page.reload()
        page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=120000)
        try:
            page.wait_for_function("() => !!heads.view && !(heads.view.job && heads.view.job.status === 'running')", timeout=35000)
            check("도는 중에 연 작업 — 헤딩 탭을 열지 않아도 끝날 때까지 읽음", seen["n"] >= 3 and page.evaluate("() => document.getElementById('paneHeads').hidden"), seen)
        except Exception as e:  # noqa: BLE001
            check("도는 중에 연 작업 — 끝날 때까지 읽음", False, f"{e} · 요약 읽기 {seen['n']}번")
        page.unroute("**/api/docs/*/headings")
        page.evaluate("() => { showTab('Heads'); headsRunOpen(3); }")  # 뒤 절은 헤딩 추출 › 추출·설정 › 3단계가 열린 채로 돈다(전에는 동그라미를 눌러 열었다)
        page.wait_for_function("() => !document.getElementById('paneHeads').hidden && !document.getElementById('headsViewRun').hidden && !document.getElementById('headsStage3').hidden")

        # ---- 2. 표를 누르면 고른 표 + 모서리 손잡이
        tbs = page.evaluate("() => xlBlocks().map((b) => ({id: b.id, rows: b.rows, cols: b.cols}))")
        big = max(tbs, key=lambda b: b["rows"])
        small = min(tbs, key=lambda b: b["rows"])
        page.mouse.move(700, 30)  # 상단 바 — 어느 표에도 올라 있지 않게
        page.wait_for_timeout(400)
        check("손잡이(두 아이콘)는 표를 누르거나 올리기 전에는 안 보임", page.locator(".tbl-corner:visible, .tbl-corner-guide:visible").count() == 0)
        page.locator(f"#doc table.tbl[data-tbl='{big['id']}'] td .para").first.click()
        page.wait_for_selector(f".tbl-corner[data-for='{big['id']}']")
        geo = page.evaluate("""(tid) => { const e = document.querySelector(`#doc table.tbl[data-tbl="${tid}"]`), t = e.getBoundingClientRect(), c = document.querySelector('.tbl-corner').getBoundingClientRect(),
            s = e.closest('.sheet').getBoundingClientRect(), mk = document.querySelector(`#doc .tbl-mark[data-for="${tid}"]`), k = mk ? mk.getBoundingClientRect() : null;
            return {dx: Math.round(c.left - t.right), dy: Math.round(c.top - t.top), w: Math.round(c.width), h: Math.round(c.height), inPaper: c.right <= s.right + 1,
                    overMark: !!k && c.left < k.right && c.right > k.left && c.top < k.bottom && c.bottom > k.top, active: tmn.active, outline: getComputedStyle(e).outlineStyle}; }""", big["id"])
        check("손잡이 = 표 오른쪽 변 바로 바깥(쪽 안 오른쪽 여백) · 표 위끝 높이 · 화면 크기 16px",
              2 <= geo["dx"] <= 6 and abs(geo["dy"]) <= 2 and geo["inPaper"] and geo["w"] == 16 and geo["h"] == 16, geo)
        check("손잡이가 표·왼쪽 여백의 표지를 가리지 않음", geo["dx"] >= 2 and not geo["overMark"], geo)
        # 둘째 아이콘(작성요령 · 표 지침 — 2026-11-12 사용자 「작성요령, 표지침을 꺼내서 아이콘 2개로」): 손잡이 바로 아래 · 같은 크기 · 같은 표
        g2 = page.evaluate("""(tid) => { const c = document.querySelector('.tbl-corner').getBoundingClientRect(), e = document.querySelector('.tbl-corner-guide'), g = e.getBoundingClientRect(),
            t = document.querySelector(`#doc table.tbl[data-tbl="${tid}"]`), tr = t.getBoundingClientRect(), s = t.closest('.sheet').getBoundingClientRect();
            return {n: document.querySelectorAll('.tbl-corner').length + document.querySelectorAll('.tbl-corner-guide').length, shown: getComputedStyle(e).display !== 'none', forTid: e.dataset.for,
                    dx: Math.round(g.left - c.left), gap: Math.round(g.top - c.bottom), w: Math.round(g.width), h: Math.round(g.height), inPaper: g.right <= s.right + 1, offTable: g.left >= tr.right + 2,
                    label: e.getAttribute('aria-label'), icon: !!e.querySelector('svg'), has: e.classList.contains('has')}; }""", big["id"])
        check("아이콘 2개 — 표 메뉴 + 작성요령 · 표 지침(손잡이 바로 아래 · 틈 2px · 16px · 쪽 안 여백 · 표를 안 가림)",
              g2["n"] == 2 and g2["shown"] and g2["forTid"] == big["id"] and g2["dx"] == 0 and g2["gap"] == 2 and g2["w"] == 16 and g2["h"] == 16 and g2["inPaper"] and g2["offTable"]
              and g2["label"] == "작성요령 · 표 지침" and g2["icon"] and not g2["has"], g2)
        check("누른 표가 고른 표(테두리)", geo["active"] == big["id"] and geo["outline"] == "solid", geo)
        caret = page.evaluate("() => document.activeElement && document.activeElement.classList.contains('para')")
        check("표 칸 글 편집은 그대로(커서가 문단에)", caret)
        page.screenshot(path=str(OUT / "2_corner.png"))

        # ---- 3. 표 메뉴
        page.locator(".tbl-corner").click()
        page.wait_for_selector(".ctx-menu[data-by='tmn']:not([hidden])")
        m = menu(page)
        texts = [x["text"] for x in m]
        check("표 메뉴 — 표 이름 · 빈 필드 제거 · 엑셀식 보기 · 서식 변환 · 표 양식 지정",
              texts[0].startswith(f"표 {big['id']} · 18×11") and any(t.startswith("빈 필드 제거하기") for t in texts) and "엑셀식 보기" in texts
              and any(t.startswith("서식으로 변환하기") for t in texts) and "이 표를 표 양식으로 지정" in texts, texts)
        check("「작성요령 · 표 지침」 은 메뉴에서 빠짐(둘째 아이콘으로 꺼냄) · 「에이전트로 표 채우기…」 는 그대로", "작성요령 · 표 지침" not in texts and "에이전트로 표 채우기…" in texts, texts)
        pos = page.evaluate("""() => { const m = document.querySelector('.ctx-menu').getBoundingClientRect(), c = document.querySelector('.tbl-corner').getBoundingClientRect(),
            g = document.querySelector('.tbl-corner-guide').getBoundingClientRect();
            return {below: m.top >= c.bottom, belowGuide: m.top >= g.bottom && m.top - g.bottom <= 6, near: Math.abs(m.left - c.left) <= 4 || m.right >= innerWidth - 10, inView: m.right <= innerWidth && m.bottom <= innerHeight}; }""")  # 창 오른끝에 닿으면 왼쪽으로 밀린다
        check("메뉴는 두 아이콘 바로 아래(둘째 아이콘을 안 가림)", pos["below"] and pos["belowGuide"] and pos["near"] and pos["inView"], pos)
        page.screenshot(path=str(OUT / "3_menu.png"))
        page.locator(".tbl-corner").click()
        page.wait_for_timeout(200)
        check("손잡이를 다시 누르면 메뉴가 닫힘", menu(page) is None)

        # ---- 3b. 둘째 아이콘 — 누르면 「작성요령 · 표 지침」 열(문서 옆 열)이 바로 열린다 · 메뉴가 열려 있었으면 닫힌다
        page.locator(".tbl-corner").click()
        page.wait_for_selector(".ctx-menu[data-by='tmn']:not([hidden])")
        page.locator(".tbl-corner-guide").click()
        page.wait_for_function("() => heads.dlg === 'tableAgent' && !!document.querySelector('.ta-wrap .ta-group')", timeout=30000)
        gv = page.evaluate("""() => ({title: document.getElementById('headsDlgTitle').textContent, groups: document.querySelectorAll('.ta-wrap .ta-group').length, active: tmn.active,
            focus: document.activeElement ? document.activeElement.id : '', shown: document.querySelector('.tbl-corner-guide').style.display !== 'none'})""")
        check("둘째 아이콘 → 「작성요령 · 표 지침 · <표>」 열(세 묶음) · 그 표가 고른 표 · 메뉴는 닫힘",
              gv["title"] == f"작성요령 · 표 지침 · {big['id']}" and gv["groups"] == 3 and gv["active"] == big["id"] and menu(page) is None and gv["shown"], gv)
        check("열을 새로 열면 초점은 그 열로(다른 단추로 열 때와 같음 — app.js headsDlg)", gv["focus"] == "headsDlg", gv)
        page.screenshot(path=str(OUT / "3b_guide.png"))
        page.evaluate("() => headsColClose(true)")
        page.wait_for_function("() => heads.dlg !== 'tableAgent'")

        # ---- 4. 빈 필드 제거하기
        page.locator(".tbl-corner").click()
        item(page, "빈 필드 제거하기").click()
        page.wait_for_selector(".ctx-menu[data-by='tmn'] button:has-text('빈 행')")
        m = menu(page)
        texts = [x["text"] for x in m]
        check("찾은 줄 — 빈 행 6개(4~9행) · 빈 열 없음", any(t.startswith("빈 행 6개 지우기 — 4~9행") for t in texts) and not any(t.startswith("빈 열") for t in texts), texts)
        check("필드 수 요약 줄", any("채우는 필드" in t and "빈 필드" in t for t in texts), texts)
        item(page, "빈 행 6개 지우기").hover()
        hit = page.evaluate("() => [...document.querySelectorAll('#doc td.tmn-hit')].map((td) => +td.dataset.r)")
        check("올리면 지울 칸을 문서에 미리 보임(3~8행 칸)", len(hit) >= 6 and set(hit) <= {3, 4, 5, 6, 7, 8}, hit)
        tip = item(page, "빈 행 6개 지우기").get_attribute("title")
        check("도움말 — 줄마다 헤더 글", "4행 「기술수요 과제명」" in tip and "6행 「기술개발의 필요성」" in tip, tip)
        page.screenshot(path=str(OUT / "4_prune.png"))
        item(page, "빈 행 6개 지우기").click()
        page.wait_for_function("(tid) => xlBlock(tid).nRows === 12", arg=big["id"], timeout=60000)
        page.wait_for_timeout(300)
        after = page.evaluate("""(tid) => ({rows: xlBlock(tid).nRows, hit: document.querySelectorAll('#doc .tmn-hit').length, toast: document.getElementById('toast').textContent, undo: state.undo, save: document.getElementById('saveState').textContent,
            has: [...document.querySelectorAll(`#doc table.tbl[data-tbl="${tid}"] .para`)].some((p) => p.textContent.includes('기술수요 과제명')),
            corner: tmnShown() && document.querySelector('.tbl-corner').dataset.for === tid, active: tmn.active})""", big["id"])
        check("빈 행 6개를 지움 — 18행 → 12행 · 미리보기 걷힘 · 알림", after["rows"] == 12 and after["hit"] == 0 and "빈 행 6개를 지웠습니다" in after["toast"] and not after["has"], after)
        check("실행 취소 1개 · 손잡이는 고른 표에 그대로", after["undo"] == 1 and after["corner"] and after["active"] == big["id"], after)
        check("고친 문서(작업에 저장) — 상단 저장 상태에 글 없음(「고친 문단 N개 · 작업에 자동 저장」 제거)", after["save"] == "", after["save"])
        cost = page.evaluate("""() => { const tds = [...document.querySelectorAll('#doc table.tbl td')]; const t0 = performance.now();
            for (let i = 0; i < 200; i += 1) tds[(i * 7) % tds.length].dispatchEvent(new MouseEvent('mouseover', {bubbles: true})); return Math.round(performance.now() - t0); }""")
        check("표 칸에 마우스 올리기 200번 — 손잡이 놓기가 배치를 다시 시키지 않음(50ms 안)", cost < 50, cost)
        page.screenshot(path=str(OUT / "4_pruned.png"))
        page.locator(".tbl-corner").click()
        item(page, "빈 필드 제거하기").click()
        page.wait_for_selector(".ctx-menu[data-by='tmn'] button.tmn-note")
        check("다시 찾으면 지울 줄 없음", any("필드가 모두 빈 행·열이 없습니다" in x["text"] for x in menu(page)), menu(page))
        item(page, "‹ 빈 필드 제거하기").click()
        check("‹ 로 표 메뉴로 돌아감", any(x["text"] == "엑셀식 보기" for x in (menu(page) or [])))
        page.keyboard.press("Escape")
        page.click("#undoBtn")
        page.wait_for_function("(tid) => xlBlock(tid).nRows === 18", arg=big["id"], timeout=60000)
        check("실행 취소로 되돌아옴(18행)", True)

        # ---- 5. 엑셀식 보기
        corner(page, big["id"])
        item(page, "엑셀식 보기").click()
        page.wait_for_function("() => heads.dlg === 'xl' && !!document.querySelector('#headsDlgBody .xl-wrap')", timeout=60000)
        check("엑셀식 보기 — 2열에 A1 격자", page.evaluate("(tid) => heads.xl.col && heads.xl.col.tid === tid", big["id"]))
        corner(page, big["id"])
        check("열려 있으면 「엑셀식 보기 닫기」", any(x["text"] == "엑셀식 보기 닫기" for x in menu(page)), menu(page))
        item(page, "엑셀식 보기 닫기").click()
        page.wait_for_function("() => heads.dlg !== 'xl'")

        # ---- 6. 서식으로 변환하기 — 표 양식 목록
        corner(page, big["id"])
        item(page, "서식으로 변환하기").click()
        page.wait_for_selector(".ctx-menu[data-by='tmn'] button.tmn-tpl")
        m = menu(page)
        tpls = [x["text"] for x in m if "tmn-tpl" in x["cls"]]
        check("표 양식 목록 = 이 표를 뺀 문서의 표", len(tpls) == len(tbs) - 1 and tpls[0].startswith(small["id"]), tpls)
        check("「자세히」 항목(2열 표 만들기 · 서식 변환)", any(x["text"].startswith("자세히") for x in m))
        page.locator(".ctx-menu[data-by='tmn'] button.tmn-tpl").first.hover()
        check("올리면 그 표 양식을 문서에서 표시", page.evaluate("(tid) => document.querySelector(`#doc table.tbl[data-tbl=\"${tid}\"]`).classList.contains('tmn-tpl-hit')", small["id"]))
        page.screenshot(path=str(OUT / "6_templates.png"))
        page.locator(".ctx-menu[data-by='tmn'] button.tmn-tpl").first.click()
        page.wait_for_function("() => document.getElementById('toast').textContent.includes('서식을 입혔습니다')", timeout=60000)
        page.wait_for_timeout(300)
        rs = page.evaluate("(tid) => ({undo: state.undo, rows: xlBlock(tid).nRows, mru: JSON.parse(localStorage.getItem('nfm.tblTpls'))[state.id].ids})", big["id"])
        check("누르면 바로 서식 입히기 — 구조 그대로 · 실행 취소 1개 · 최근 쓴 표 양식에 기억", rs["rows"] == 18 and rs["undo"] == 1 and rs["mru"] == [small["id"]], rs)
        corner(page, big["id"])
        item(page, "서식으로 변환하기").click()
        page.wait_for_selector(".ctx-menu[data-by='tmn'] button.tmn-tpl")
        check("다시 열면 「최근 쓴 표 양식」 이 맨 위", [x["text"] for x in menu(page)][1:3] == ["최근 쓴 표 양식", f"{small['id']} · 1×3 · 별첨"], [x["text"] for x in menu(page)])
        item(page, "자세히").click()
        page.wait_for_function("() => heads.dlg === 'tableMake'")
        check("「자세히」 → 2열 표 만들기 · 서식 변환(원본 = 이 표)", page.evaluate("(tid) => tmk.kind === 'table' && tmk.table === tid", big["id"]))
        page.evaluate("() => headsColClose(true)")
        page.click("#undoBtn")
        page.wait_for_function("() => state.undo === 0", timeout=60000)

        # ---- 7. 이 표를 표 양식으로 지정
        corner(page, small["id"])
        item(page, "이 표를 표 양식으로 지정").click()
        mem = page.evaluate("() => ({tpl: JSON.parse(localStorage.getItem('nfm.tblMake'))[state.id].tpl, toast: document.getElementById('toast').textContent})")
        check("표 양식으로 지정 — 2열 표 양식 기억과 같은 자리", mem["tpl"] == small["id"] and "표 양식으로 지정" in mem["toast"], mem)
        page.locator(f"#doc table.tbl[data-tbl='{small['id']}'] td").first.hover()  # 메뉴는 표 오른쪽 여백의 손잡이 아래에 열린다 — 마우스를 표 위로 되돌린다
        page.evaluate("() => document.querySelector('#doc .sheet').dispatchEvent(new MouseEvent('mousedown', {bubbles: true}))")  # 쪽 여백(표 밖)을 누름
        still = page.evaluate("() => ({active: tmn.active, hover: tmn.hover, corner: tmnShown(), marked: document.querySelectorAll('#doc .tmn-active').length})")
        check("표 밖을 누르면 고른 표가 풀림(마우스가 올라 있는 표에는 손잡이가 남음)", still["active"] is None and still["marked"] == 0 and still["corner"] and still["hover"] == small["id"], still)
        page.mouse.move(700, 30)  # 문서 밖(상단 바)으로
        page.wait_for_timeout(500)
        check("마우스가 표를 떠나면 손잡이(두 아이콘)도 사라짐", page.locator(".tbl-corner:visible, .tbl-corner-guide:visible").count() == 0)
        page.locator(f"#doc table.tbl[data-tbl='{big['id']}'] td").nth(5).hover()
        page.wait_for_selector(f".tbl-corner[data-for='{big['id']}']")
        check("누르지 않고 마우스만 올려도 그 표에 손잡이", page.evaluate("() => tmn.active") is None)
        # 긴 표를 내려 봐도(표 위끝이 보기 밖) 손잡이는 보기 위끝에 붙어 따라온다 · 표가 다 지나가면 감춤
        page.locator(f"#doc table.tbl[data-tbl='{big['id']}'] td .para").first.click()
        page.evaluate("""(tid) => { const sc = document.getElementById('scroller'), t = document.querySelector(`#doc table.tbl[data-tbl="${tid}"]`);
            sc.scrollTop += t.getBoundingClientRect().top - sc.getBoundingClientRect().top + 200; }""", big["id"])
        page.mouse.move(700, 30)
        page.wait_for_timeout(600)
        stuck = page.evaluate("""(tid) => { const c = document.querySelector('.tbl-corner'), r = c.getBoundingClientRect(), s = document.getElementById('scroller').getBoundingClientRect(),
            t = document.querySelector(`#doc table.tbl[data-tbl="${tid}"]`).getBoundingClientRect();
            g = document.querySelector('.tbl-corner-guide'), gr = g.getBoundingClientRect();
            return {shown: tmnShown(), top: Math.round(r.top + r.height / 2 - s.top), dx: Math.round(r.left - t.right), tableTop: Math.round(t.top - s.top),
                    guide: g.style.display !== 'none' && Math.round(gr.left - r.left) === 0 && Math.round(gr.top - r.bottom) === 2}; }""", big["id"])
        check("표 위끝이 보기 밖이면 손잡이는 보기 위끝(표 오른쪽 변 바깥)에 붙음 · 둘째 아이콘도 그 아래에", stuck["shown"] and stuck["tableTop"] < 0 and 9 <= stuck["top"] <= 12 and 2 <= stuck["dx"] <= 6 and stuck["guide"], stuck)
        page.evaluate("() => { const sc = document.getElementById('scroller'); sc.scrollTop = sc.scrollHeight; }")
        page.wait_for_timeout(600)
        gone = page.evaluate("""(tid) => ({hidden: !tmnShown(), below: document.querySelector(`#doc table.tbl[data-tbl="${tid}"]`).getBoundingClientRect().bottom
            < document.getElementById('scroller').getBoundingClientRect().top})""", big["id"])
        check("표가 보기 밖으로 다 지나가면 손잡이를 감춤(지나가지 않았으면 그대로)", gone["hidden"] == gone["below"], gone)
        page.evaluate("() => { document.getElementById('scroller').scrollTop = 0; }")
        page.wait_for_timeout(400)

        # ---- 7b. 프로젝트 구성에 맞추기…(spec_테이블매니저 ② §9 「표 하나만 프로젝트 구성에 맞추기」) — 연구개발과제 문서에서만 항목이 있다 · 지원 양식이 아니면 까닭 글 · 일반 문서에는 항목 없음
        DIV = "프로젝트 구성에 맞추기"
        corner(page, big["id"])
        m = menu(page)
        # 이 견본(기술수요조사서)은 양식을 못 읽어 작업 종류가 비어 있다(연구개발과제가 아님) — 항목이 없어야 한다
        check("작업 종류가 빈 문서(양식을 못 읽음) — 「프로젝트 구성에 맞추기…」 항목 자체가 없음", not page.evaluate("() => taskRnd()") and not any(x["text"].startswith(DIV) for x in m), [x["text"] for x in m])
        page.keyboard.press("Escape")
        page.evaluate("() => { window.__task = state.task; state.task = { ...(state.task || {}), kind: 'rnd' }; }")   # 작업 종류만 연구개발과제로(양식은 여전히 지원 밖) — 까닭 글의 길
        corner(page, big["id"])
        m = menu(page)
        check("연구개발과제 문서 — 표 메뉴에 「프로젝트 구성에 맞추기…」(▸)", page.evaluate("() => taskRnd()") and any(x["text"] == f"{DIV}…▸" for x in m), [x["text"] for x in m])
        item(page, f"{DIV}…").click()
        page.wait_for_selector(".ctx-menu[data-by='tmn'] button.tmn-note", timeout=120000)
        m = menu(page)
        check("지원 양식이 아닌 문서(기술수요조사서) — 자리 대신 까닭 글 · 머리는 ‹ 돌아가기",
              m[0]["text"] == f"‹ {DIV} · {big['id']}" and any("프로젝트 구성 자동 반영을 지원하지 않습니다" in x["text"] for x in m), [x["text"] for x in m])
        item(page, f"‹ {DIV}").click()
        check("‹ 로 표 메뉴로 돌아감(프로젝트 구성에 맞추기)", any(x["text"] == "엑셀식 보기" for x in (menu(page) or [])))
        page.keyboard.press("Escape")
        page.evaluate("() => { state.task = { ...(state.task || {}), kind: 'general' }; }")   # 원래 값(window.__task)은 위에서 떠 두었다
        corner(page, big["id"])
        check("일반 문서(작업 종류 = 일반 문서) — 「프로젝트 구성에 맞추기…」 항목 자체가 없음", not any(x["text"].startswith(DIV) for x in menu(page)), [x["text"] for x in menu(page)])
        page.keyboard.press("Escape")
        page.evaluate("() => { state.task = window.__task; }")

        # ---- 7c. 연구개발계획서 양식(지원 양식) — 진짜 끝점으로: 자리 목록 → 그 자리만의 변경 계획(문서는 그대로) → 패널의 「반영」(기존 길) → 실행 취소
        fid = requests.post(f"{base}/api/docs?new=1", files={"file": (FORM.name, FORM.read_bytes())}, timeout=300).json()["docId"]
        mem0 = requests.get(f"{base}/api/docs/{fid}/divisions/members?targets=1", timeout=300).json()
        check("프로젝트 구성 값이 없으면 서버의 targets 는 null(기본값으로 센 수를 내지 않는다)", mem0["targets"] is None and mem0["supported"], mem0.get("targets"))
        requests.put(f"{base}/api/docs/{fid}/divisions/settings", json={"values": VALUES}, timeout=120).raise_for_status()   # 화면이 문서를 열기 전에 — 화면의 값(dv.values)이 이 값으로 읽힌다
        by = {}
        for g in mem0["groups"]:
            if g["where"]["table"]:
                by.setdefault(g["where"]["table"], []).append(g)
        # 기관 행 2개 + 단계-차년도 행 4개가 든 표(기관 행 안에 단계-차년도 행) — 값에 맞추면 기관 3 · 차년도 5
        ftid, gs = next((k, v) for k, v in by.items() if sorted((g["dim"], g["kind"], g["count"]) for g in v) == [("org", "rows", 2), ("stageYear", "rows", 4)])
        org = next(g for g in gs if g["dim"] == "org")
        used = {"tables": sorted(by), "cells": sorted({g["where"]["cell"] for g in mem0["groups"] if g["where"]["cell"]})}
        page.evaluate("(w) => { location.hash = `w=${w}`; }", fid)
        page.reload()
        page.wait_for_function("""(a) => typeof state !== 'undefined' && state.id === a.id && !!document.querySelector(`#doc table.tbl[data-tbl="${a.tid}"] td .para`)""", arg={"id": fid, "tid": ftid}, timeout=300000)
        page.wait_for_timeout(1500)
        none = page.evaluate("""(u) => { const b = xlBlocks().find((b) => b.depth === 1 && b.rows * b.cols > 1 && !u.tables.includes(b.id) && !(xlBlock(b.id).cells || []).some((c) => u.cells.includes(c.id)));
            return b ? b.id : null; }""", used)
        check("양식에서 구분 기준 자리가 없는 표를 하나 찾음(검사 준비)", bool(none), none)
        if none:
            corner_far(page, none)
            item(page, f"{DIV}…").click()
            page.wait_for_selector(".ctx-menu[data-by='tmn'] button.tmn-note", timeout=120000)
            check("자리가 없는 표 — 「이 표에는 프로젝트 구성으로 늘리고 줄일 자리가 없습니다」",
                  any(x["text"] == "이 표에는 프로젝트 구성으로 늘리고 줄일 자리가 없습니다" for x in menu(page)), [x["text"] for x in menu(page)])
            page.keyboard.press("Escape")
        # 프로젝트 구성 값이 없을 때의 목록 — 응답의 targets 만 null 로 바꿔 흉내(값은 위에서 넣어 두었다)
        members_url = re.compile(r"/divisions/members\?targets=1")

        def no_config(route):
            resp = route.fetch()
            body = resp.json()
            body["targets"] = None
            route.fulfill(response=resp, json=body)
        page.route(members_url, no_config)
        corner_far(page, ftid)
        item(page, f"{DIV}…").click()
        page.wait_for_selector(".ctx-menu[data-by='tmn'] button:has-text('프로젝트 구성 열기')", timeout=120000)
        texts = [x["text"] for x in menu(page)]
        check("프로젝트 구성 값이 없을 때 — 「프로젝트 구성을 먼저 정하세요」 · 자리는 지금 수만 · 「프로젝트 구성 열기」",
              "프로젝트 구성을 먼저 정하세요" in texts and "기관 행 — 지금 2개" in texts and "단계-차년도 행 — 지금 4개" in texts and not any("→ 프로젝트 구성" in t for t in texts), texts)
        page.keyboard.press("Escape")
        page.unroute(members_url)
        # 자리 목록(진짜 응답) — 「지금 n개 → 프로젝트 구성 m개」
        corner_far(page, ftid)
        item(page, f"{DIV}…").click()
        page.wait_for_selector(".ctx-menu[data-by='tmn'] button:has-text('→ 프로젝트 구성')", timeout=120000)
        m = menu(page)
        texts, off = [x["text"] for x in m], {x["text"]: x["disabled"] for x in m}
        check("자리 목록 — 「기관 행 — 지금 2개 → 프로젝트 구성 3개」 · 「단계-차년도 행 — 지금 4개 → 프로젝트 구성 5개」(누를 수 있음) · 「이 표의 자리 2곳」",
              off.get("기관 행 — 지금 2개 → 프로젝트 구성 3개") is False and off.get("단계-차년도 행 — 지금 4개 → 프로젝트 구성 5개") is False and any(t.startswith("이 표의 자리 2곳") for t in texts), texts)
        item(page, "기관 행 — 지금 2개").hover()
        hit = page.evaluate("() => ({div: document.querySelectorAll('#doc td.tmn-div-hit').length, red: document.querySelectorAll('#doc .tmn-hit').length})")
        check("올리면 그 자리의 항목 머리 칸을 문서에 칠함(파랑 — 지울 칸의 빨강이 아님)", hit["div"] >= 2 and hit["red"] == 0, hit)
        page.screenshot(path=str(OUT / "7c_places.png"))
        sizes_js = "() => ({rev: state.serverRev, undo: state.undo, sizes: Object.fromEntries(xlBlocks().map((b) => [b.id, [b.rows, b.cols]]))})"
        before = page.evaluate(sizes_js)
        with page.expect_request(lambda r: r.method == "POST" and r.url.endswith("/divisions/plan"), timeout=120000) as req:
            item(page, "기관 행 — 지금 2개").click()
        sent = req.value.post_data_json
        check("고른 자리의 key 로 기존 계획 끝점을 부름(only) · 값은 화면이 읽은 프로젝트 구성",
              sent.get("only") == org["key"] and sent.get("skip") == [] and sent["values"]["stages"] == [2, 3] and sent["values"]["orgs"]["lead"] == "인텍", sent)
        page.wait_for_function("() => heads.dlg === 'divisions' && !!dv.plan && !dv.busy && !!document.getElementById('divListTable')", timeout=240000)
        rows_js = "() => document.querySelectorAll('#headsDlgBody table.mini tbody tr.go').length"
        v = page.evaluate("""() => ({only: dv.plan.only, table: dv.plan.table && dv.plan.table.id, all: dv.plan.candidates.length, rows: document.querySelectorAll('#headsDlgBody table.mini tbody tr.go').length,
            pressed: document.getElementById('divListTable').getAttribute('aria-pressed'), label: document.getElementById('divListTable').textContent, note: document.getElementById('headsDlgNote').textContent,
            title: document.getElementById('headsDlgTitle').textContent, rev: state.serverRev, undo: state.undo, kind: divPlanState().kind, hit: document.querySelectorAll('#doc td.tmn-div-hit').length})""")
        check("변경 계획 — 문서 옆 목록(기존 「바꿀 자리」)이 이 표의 자리만 · 「고른 자리 … 만의 계획」 · 반영할 수 있음",
              v["only"] == org["key"] and v["table"] == ftid and 2 <= v["rows"] < v["all"] and v["pressed"] == "true" and v["label"] == f"표 {ftid} 의 자리만"
              and v["title"] == "프로젝트 구성 — 바꿀 자리" and "고른 자리와 그 안쪽 자리만의 계획" in v["note"] and v["kind"] == "ready", v)
        check("계획은 문서를 바꾸지 않음(문서 차례 · 실행 취소 수 그대로) · 메뉴가 닫히면 미리보기도 걷힘", v["rev"] == before["rev"] and v["undo"] == before["undo"] and v["hit"] == 0 and page.evaluate(sizes_js)["sizes"] == before["sizes"], v)
        page.screenshot(path=str(OUT / "7c_plan.png"))
        page.click("#divListTable")
        page.wait_for_function("() => document.getElementById('divListTable').getAttribute('aria-pressed') === 'false'")
        check("단추를 누르면 문서의 모든 자리(계획은 그대로)", page.evaluate(rows_js) == v["all"], [page.evaluate(rows_js), v["all"]])
        page.click("#divListTable")
        page.wait_for_function("() => document.getElementById('divListTable').getAttribute('aria-pressed') === 'true'")
        page.click("#headsDlgFoot [data-div-go]")   # 반영 단추는 패널의 실행 묶음 하나뿐 — 목록의 발은 그리로 보낸다(spec_구분_기준 ② §22)
        page.wait_for_function("() => document.activeElement && document.activeElement.id === 'divApplyButton'", timeout=30000)
        page.click("#divApplyButton")
        page.wait_for_function("(a) => !!dv.result && !dv.busy && state.inflight === 0 && !!xlBlock(a.tid) && xlBlock(a.tid).nRows > a.rows", arg={"tid": ftid, "rows": before["sizes"][ftid][0]}, timeout=240000)
        page.wait_for_timeout(500)
        after = page.evaluate(sizes_js)
        res = page.evaluate("() => ({title: document.getElementById('headsDlgTitle').textContent, rows: document.querySelectorAll('#headsDlgBody table.mini tbody tr.go').length})")
        check("패널의 「반영」(기존 길) — 이 표의 행만 늘고 다른 표는 그대로 · 실행 취소 1개",
              after["sizes"][ftid][0] > before["sizes"][ftid][0] and after["sizes"][ftid][1] == before["sizes"][ftid][1]
              and all(after["sizes"].get(k) == s for k, s in before["sizes"].items() if k != ftid) and after["undo"] == before["undo"] + 1,
              {"표": [before["sizes"][ftid], after["sizes"][ftid]], "undo": [before["undo"], after["undo"]]})
        check("반영 결과 목록도 이 표의 자리만", res["title"] == "프로젝트 구성 — 반영 결과" and res["rows"] == v["rows"], res)
        page.screenshot(path=str(OUT / "7c_applied.png"))
        page.click("#undoBtn")
        page.wait_for_function("(a) => state.undo === a.undo && !!xlBlock(a.tid) && xlBlock(a.tid).nRows === a.rows", arg={"tid": ftid, "rows": before["sizes"][ftid][0], "undo": before["undo"]}, timeout=120000)
        check("실행 취소로 되돌아옴(그 표의 행 수)", True)

        # ---- 8. docx — hwpx 전용 항목은 꺼짐
        page.evaluate("() => closeDoc()")
        open_sample(page, DOCX)
        page.wait_for_timeout(600)
        tid = page.evaluate("() => xlBlocks().sort((a, b) => b.rows - a.rows)[0].id")
        corner(page, tid)
        m = menu(page)
        dis = {x["text"].replace("▸", ""): x["disabled"] for x in m}
        check("docx — 빈 필드 제거·서식 변환·표 양식 지정은 꺼짐, 엑셀식 보기는 켜짐",
              dis.get("빈 필드 제거하기") and dis.get("서식으로 변환하기") and dis.get("이 표를 표 양식으로 지정") and dis.get("엑셀식 보기") is False, dis)
        check("docx — 「프로젝트 구성에 맞추기…」 는 항목 자체가 없음(연구개발과제 hwpx 문서만)", not any(k.startswith("프로젝트 구성에 맞추기") for k in dis), dis)
        page.keyboard.press("Escape")
        page.locator(".tbl-corner-guide").click()
        page.wait_for_function("() => heads.dlg === 'tableAgent' && !!document.querySelector('.ta-wrap')", timeout=30000)
        check("docx — 둘째 아이콘(작성요령 · 표 지침)은 켜져 있음", page.evaluate("() => document.getElementById('headsDlgTitle').textContent") == f"작성요령 · 표 지침 · {tid}")
        page.evaluate("() => headsColClose(true)")

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
