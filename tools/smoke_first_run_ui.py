"""첫 분석(spec_작업 ② §9)·LLM 검토 취합(spec_구분_기준 ② §14) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_first_run_ui.py <그림·임시 폴더> [--rnd] [--port 18171]

- 새 작업(예제를 화면에서 엶): 헤딩 탭을 열지 않아도 `POST …/headings {first: true}` 한 번으로 2·3단계 결과·개요 편집이 생기고, 이름 줄의 분석 상태가 「헤딩 ✓ · 템플릿 ✓ · 서식 n/m · 표 ✓ · LLM 안 함」 이 된다.
  **구분 기준 LLM 검토(`POST …/divisions/review`)는 부르지 않는다**(2026-11-15 — spec_작업 ② §20 「구분 기준은 옵션」: 전에는 {auto: true} 로 한 번 불렀다). 같은 예제를 다시 열면(이어 열기) 다시 부르지 않는다.
- 구분 기준 탭: 「LLM 검토」 → 2열 「구분 기준 — LLM 검토 결과」 → 「LLM 검토 실행」(응답은 page.route 로 끼운 가짜 — 재검토 1 + 빠진 자리 2) → 한 표·단추 글.
- --rnd: 연구개발계획서 양식(지원 양식)을 새 작업으로 열어 첫 분석이 끝나는 시간과 쪽 여백 표시 수를 잰다(검토는 안 부름 — 이름 줄에 「구분 기준 안 함」). 4분쯤 더 걸린다."""
import argparse
import json
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
ap.add_argument("--rnd", action="store_true")
ap.add_argument("--port", type=int, default=18171)
args = ap.parse_args()
OUT = Path(args.out).resolve()
SMALL, RND = "기술수요조사서.hwpx", "연구개발계획서_양식.hwpx"

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
errors, fails, posts, reviews = [], [], [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:300] if detail != "" else ""), flush=True)
    if not ok:
        fails.append(name)


def on_request(req):
    if req.method == "POST" and (req.url.endswith("/headings") or req.url.endswith("/divisions/review")):
        posts.append((req.url.rsplit("/api/docs/", 1)[-1].split("/", 1)[-1], req.post_data or ""))


def on_response(res):
    if res.request.method == "POST" and res.url.endswith("/divisions/review"):
        try:
            reviews.append((res.status, res.json()))
        except Exception as e:  # noqa: BLE001
            reviews.append((res.status, str(e)))


def open_sample(page, name, timeout=240000):
    page.evaluate("() => { const s = document.getElementById('sampleSection'); s.hidden = false; s.open = true; }")
    page.evaluate("(n) => document.querySelector(`.sample[aria-label=\"예제 ${n} 열기\"]`).click()", name)
    page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=timeout)


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
        page = browser.new_page(viewport={"width": 1700, "height": 1000})
        page.add_init_script("try { localStorage.setItem('nfm.toolMore', '1'); } catch (e) {}")  # 패널 머리 오른쪽 묶음(검증·PDF·기록)을 펴 둔다 — 접힘은 smoke_panel_head_ui.py(2026-11-16)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("request", on_request)
        page.on("response", on_response)
        page.goto(base)
        page.wait_for_selector("#drop")

        # ---- 1. 새 작업 — 첫 분석이 저절로
        open_sample(page, SMALL)
        try:
            page.wait_for_function("() => { const t = document.getElementById('toast'); return !t.hidden && t.textContent.includes('첫 분석'); }", timeout=10000)
            check("새 작업 알림 「첫 분석」", True)
        except Exception:  # noqa: BLE001
            check("새 작업 알림 「첫 분석」", False, page.evaluate("() => document.getElementById('toast').textContent"))
        page.wait_for_function(FIRST_DONE, timeout=90000)
        check("헤딩 탭을 열지 않음", page.evaluate("() => document.getElementById('paneHeads').hidden"))
        job = page.evaluate("() => heads.view.job")
        check("첫 분석 작업 — first · 끝남", bool(job and job["first"] and job["status"] == "done" and job["stage"] == 3), job)
        runs = page.evaluate("() => heads.view.runs.map((r) => [r.stage, r.llm])")
        check("실행 = 1 → 2 → 3단계, 모두 스크립트", runs == [[1, False], [2, False], [3, False]], runs)
        page.wait_for_function("() => heads.outline != null", timeout=30000)
        check("개요 편집 켜짐(오버레이)", page.evaluate("() => Object.keys(heads.outline.lines).length") >= 0,
              page.evaluate("() => Object.keys(heads.outline.lines).length"))
        check("단축키 단추에 개요 편집 키 켜짐", page.get_attribute("#shortcutsBtn", "data-outline") == "1",  # 옛 #editHint 글 「개요 줄: …」 자리(shortcuts.js)
              page.get_attribute("#shortcutsBtn", "data-outline"))
        print("INFO 쪽 여백 표시(.tpl-mark)", page.locator("#doc .tpl-mark").count(), flush=True)
        heads_posts = [p for p in posts if p[0] == "headings"]
        check("POST …/headings 는 {first: true} 한 번", len(heads_posts) == 1 and json.loads(heads_posts[0][1]) == {"first": True}, heads_posts)
        page.wait_for_timeout(2500)  # 전에는 이 사이 {auto: true} 검토가 한 번 나갔다
        rev_posts = [p for p in posts if p[0] == "divisions/review"]
        check("첫 분석은 구분 기준 LLM 검토를 부르지 않는다(POST …/divisions/review 0번 — ② §20 「구분 기준은 옵션」)", not rev_posts and not reviews, [rev_posts, reviews])
        page.wait_for_function("() => document.getElementById('docStatus').dataset.base === 'done'", timeout=15000)
        chips = page.evaluate("() => [...document.querySelectorAll('#docStatus .ds-chip')].map((c) => [...c.querySelectorAll('.ds-text, .ds-mark')].map((e) => e.textContent).join(' '))")
        # 2026-11-16 이름 줄이 넷(헤딩 · 템플릿 · 서식 · 표) + LLM 으로 넓어짐(spec_작업 ② §20) — 서식은 「맞춘 레벨/레벨 수」 라 수는 예제마다 다르다
        check("이름 줄의 분석 상태 — 「헤딩 ✓ · 템플릿 ✓ · 서식 n/m · 표 ✓ · LLM 안 함」 · 「분석」 단추 없음",
              len(chips) == 5 and chips[:2] == ["헤딩 ✓", "템플릿 ✓"] and re.fullmatch(r"서식 \d+/\d+", chips[2]) and chips[3:] == ["표 ✓", "LLM 안 함"] and page.locator("#docStatus .ds-go").count() == 0, chips)
        page.click("#tabHeads")
        page.wait_for_function("() => !document.getElementById('paneHeads').hidden && document.querySelector('#headsOverview .result-metric') != null", timeout=30000)
        page.wait_for_timeout(1500)
        check("헤딩 탭을 열어도 다시 추출하지 않음", len([p for p in posts if p[0] == "headings"]) == 1, posts)
        page.click("#headsTabRun")
        page.click("#headsStageTab3")  # 추출·설정은 단계 탭 — 첫 분석 작업 줄은 3단계 카드에(spec_헤딩_추출 ② §7 「단계 탭」)
        check("3단계 카드에 첫 분석 작업 줄", page.is_visible("#heads3Job") and "첫 분석(2·3단계)" in page.inner_text("#heads3Job"), page.inner_text("#heads3Job")[:80])
        page.click("#tabLog")
        page.wait_for_function("() => document.querySelectorAll('#logList li').length > 0", timeout=15000)
        check("기록 탭에 「2단계(첫 분석)」", "2단계(첫 분석)" in page.inner_text("#logList") and "3단계(첫 분석)" in page.inner_text("#logList"), page.inner_text("#logList")[:200])
        page.screenshot(path=str(OUT / "1_first_run.png"))

        # ---- 2. 이어 연 작업 — 첫 분석을 다시 부르지 않음
        n_posts = len(posts)
        page.evaluate("() => closeDoc()")
        open_sample(page, SMALL)
        page.wait_for_function("() => { const t = document.getElementById('toast'); return !t.hidden && t.textContent.includes('이어서'); }", timeout=15000)
        page.wait_for_timeout(1500)
        check("이어 연 작업은 첫 분석 없음", len(posts) == n_posts, posts[n_posts:])

        # ---- 3. 구분 기준 탭 — LLM 검토(두 검토 → 한 목록). 응답은 가짜(서버는 LLM 끔)
        ids = page.evaluate("""() => { const ps = [], ts = []; const walk = (bs) => { for (const b of bs) { if (b.type === 'paragraph' && (b.text || '').trim()) ps.push(b.id);
            if (b.type === 'table') { ts.push(b.id); for (const c of b.cells || []) walk(c.blocks || []); } } }; walk(state.blocks); return { p: ps.slice(0, 2), t: ts[0], rev: state.serverRev }; }""")
        p1, p2 = ids["p"]
        call = {"backend": "fake", "model": "m", "effort": "medium", "ms": 31000, "costUsd": 0.11, "error": None}
        m_items = [{"id": p1, "kind": "paragraph", "dim": "stage", "dimName": "단계", "title": "", "text": "다. 2단계 추진 계획", "size": "", "path": ["1. 개요"],
                    "pattern": "절: 단계마다", "reason": "단계 제목 줄", "confidence": "high"},
                   {"id": ids["t"], "kind": "table", "dim": "org", "dimName": "기관", "title": "나. 연구지원인력 현황", "text": "번호 · 성명 · 소속 기관", "size": "3x4",
                    "path": ["7. 참여 인력"], "pattern": "행: 소속 기관마다", "reason": "소속 기관 열", "confidence": "medium"},
                   {"id": p2, "kind": "paragraph", "dim": "org", "dimName": "기관", "title": "", "text": "가. 기관명: (역할: )", "size": "", "path": [],
                    "pattern": "절: 기관마다 표 하나", "reason": "가./나. 기관명", "confidence": "low"}]
        applied = [{"action": "add", "hintId": "h1", "para": p1, "dim": "stage", "value": "2단계", "reason": "형제"}]
        fake = {"at": time.time(), "rev": ids["rev"], "ran": {"review": True, "missing": True}, "why": {}, "errors": {},
                "review": {"applied": applied, "skipped": [], "summary": "표시한 자리의 형제 하나를 더했습니다.", "call": call},
                "missing": {"missing": m_items, "skipped": [], "summary": "묶음 밖에 두 곳이 더 보입니다.", "sent": {"tables": 3, "paragraphs": 5}, "call": call},
                "items": [{**m_items[0], "sources": ["review", "missing"], "reason": "형제 · 단계 제목 줄", "action": "add", "value": "2단계", "hintId": "h1", "note": ""},
                          {**m_items[1], "sources": ["missing"], "action": None, "value": "", "hintId": "", "note": ""},
                          {**m_items[2], "sources": ["missing"], "action": None, "value": "", "hintId": "", "note": ""}],
                "costUsd": 0.22, "ms": 31000, "hints": [], "detail": "divisions/review_x"}
        page.route("**/divisions/review", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(fake, ensure_ascii=False)))
        page.select_option("#panelTask", "rnd")  # 패널 머리의 「작업」 목록(상단 바의 옛 #taskKind 는 2026-11-11 없앰 — 고르면 그 내용이 바로 열림 · 탭 띠의 「연구개발과제」 탭은 2026-11-12 없앰) · 작은 문서는 국가R&D 양식이 아니라 작업 종류가 비어 있다(spec_작업 ② §10) — 작업 종류를 골라 연다
        page.wait_for_selector("#divMarksBar")
        bar = lambda text: page.locator("#divMarksBar button", has_text=text).count()  # noqa: E731
        check("표시 줄에 「LLM 검토」 단추", page.evaluate("() => [...document.querySelectorAll('#divMarksBar button')].filter((b) => b.textContent.trim() === 'LLM 검토').length") == 1)
        check("「빠진 자리 검토」 단추는 그대로 · 표시 줄의 「LLM 재검토」 는 없음", bar("빠진 자리 검토") == 1 and bar("LLM 재검토") == 0)
        page.evaluate("() => [...document.querySelectorAll('#divMarksBar button')].find((b) => b.textContent.trim() === 'LLM 검토').click()")
        page.wait_for_function("() => !document.getElementById('headsDlg').hidden", timeout=10000)
        check("2열 제목", page.inner_text("#headsDlgTitle").strip() == "구분 기준 — LLM 검토 결과", page.inner_text("#headsDlgTitle"))
        check("아직 검토 전 안내", "아직 검토하지 않았습니다" in page.inner_text("#headsDlgBody"))
        page.locator("#headsDlgFoot button", has_text="LLM 검토 실행").click()
        page.wait_for_function("() => document.querySelectorAll('#headsDlgBody table.mini tbody tr.go').length === 3", timeout=20000)
        rows = page.evaluate("() => [...document.querySelectorAll('#headsDlgBody table.mini tbody tr.go')].map((tr) => [...tr.cells].map((td) => td.innerText.replace(/\\s+/g, ' ').trim()))")
        # 줄 차례(2026-11-11 — spec_구분_기준 ② §13·§14 「후보 줄 차례」): 「자리로 추가」 할 수 있는 문단 후보 → 재검토 줄 → 표 후보
        check("문단 후보는 「자리로 추가」 — 맨 위", rows[0][0].startswith("빠진 자리") and rows[0][4] == "자리로 추가", rows[0])
        check("한 표 3줄 — 같은 문단은 한 줄(재검토 + 빠진 자리)", rows[1][0] == "재검토 + 빠진 자리 높음" and rows[1][1] == "단계 · 2단계" and rows[1][4] == "반영됨", rows[1])
        check("표 후보는 표시만 — 맨 아래", rows[2][0] == "빠진 자리 중간" and "표 3x4" in rows[2][2] and rows[2][4] == "표시만", rows[2])
        check("목록 위 한 줄 — 문단 후보 수·표 후보 수", "문단 후보 1개" in page.inner_text("#headsDlgBody .dv-cand-note") and "표 후보 1개" in page.inner_text("#headsDlgBody .dv-cand-note"), page.inner_text("#headsDlgBody .dv-cand-note"))
        check("위 요약 줄", "재검토 반영 1" in page.inner_text("#headsDlgTools") and "빠진 자리 후보 3" in page.inner_text("#headsDlgTools") and "$0.22" in page.inner_text("#headsDlgTools"),
              page.inner_text("#headsDlgTools"))
        check("LLM 판단 글 둘", page.locator("#headsDlgBody .dv-llm-last").count() == 2)
        check("표시 줄 단추가 「검토 결과 3」 · 「빠진 자리 후보 3」", bar("검토 결과 3") == 1 and bar("빠진 자리 후보 3") == 1,
              page.evaluate("() => [...document.querySelectorAll('#divMarksBar button')].map((b) => b.textContent.trim())"))
        check("2열 단추가 「다시 검토」", page.locator("#headsDlgFoot button", has_text="다시 검토").count() == 1)
        over = page.evaluate("() => { const b = document.getElementById('headsDlgBody'); return b.scrollWidth - b.clientWidth; }")
        check("2열 가로 넘침 없음", over <= 1, over)
        page.screenshot(path=str(OUT / "3_review_list.png"))
        page.locator("#headsDlgBody table.mini tbody tr.go").first.click()
        page.wait_for_timeout(600)
        check("줄을 누르면 그 줄이 골라짐", page.locator("#headsDlgBody tr.go.sel").count() == 1)
        page.unroute("**/divisions/review")

        # ---- 4. (선택) 연구개발계획서 양식 — 새 작업으로 열어 첫 분석 시간
        if args.rnd:
            page.evaluate("() => closeDoc()")
            reviews.clear()
            t0 = time.time()
            open_sample(page, RND)
            t_doc = time.time() - t0
            page.wait_for_function(FIRST_DONE, timeout=240000)
            t_first = time.time() - t0
            page.wait_for_function("() => heads.outline != null && heads.graph != null", timeout=120000)
            page.wait_for_function("() => document.querySelectorAll('#doc .tpl-mark').length > 0", timeout=120000)
            t_marks = time.time() - t0
            c = page.evaluate("() => ({ nodes: heads.view.stage2.counts.nodes, templates: heads.view.stage2.counts.templates, tables: heads.view.stage3.counts.tables, marks: document.querySelectorAll('#doc .tpl-mark').length })")
            print(f"INFO 양식: 문서 그림 {t_doc:.1f}s · 첫 분석 끝 {t_first:.1f}s · 쪽 여백 표시 {t_marks:.1f}s · {c}", flush=True)
            check("양식 — 2·3단계 결과", c["nodes"] > 500 and c["tables"] > 50 and c["marks"] > 100, c)
            page.wait_for_timeout(2500)
            check("양식(지원 양식) — 첫 분석은 구분 기준 LLM 검토를 부르지 않는다", not reviews, reviews)
            chips = page.evaluate("() => [...document.querySelectorAll('#docStatus .ds-chip')].map((c) => [...c.querySelectorAll('.ds-text, .ds-mark')].map((e) => e.textContent).join(' '))")
            check("양식 — 이름 줄 「헤딩 ✓ · 표 ✓ · LLM 안 함 · 구분 기준 안 함」", chips == ["헤딩 ✓", "표 ✓", "LLM 안 함", "구분 기준 안 함"], chips)
            page.screenshot(path=str(OUT / "4_rnd_first_run.png"))

        bad = [e for e in errors if "Failed to load resource" not in e]
        check("콘솔 오류 0", not bad, bad[:5])
        browser.close()
finally:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()

print(f"\n{'실패 ' + str(len(fails)) + '개: ' + ' / '.join(fails) if fails else '모두 통과'}")
sys.exit(1 if fails else 0)
