"""지침 설정 페이지(spec_양식작성 ② §5-10 — app/static/guides.html · guides.js · guides.css · app/guides_page_api.py) 화면 확인 — 임시 서버(임시 작업 폴더 · 임시 설정 파일 · 저장소 forms/ 의 사본, PDF·LLM 끔)를 스스로 띄운다.
끝점은 모두 진짜(흉내 없음).

- 입구: 시작 화면의 에이전트 창 머리 — 톱니(에이전트 설정) 바로 옆 「지침 설정」(#agentGuides → /guides · 새 탭).
- 페이지 /guides: 상단 줄(제목 · 탭 둘 「판단 지침」 · 「양식별」 · 글 수) · account/chip.js 가 먼저 · app.js 를 읽지 않음 · 목차(전체 보기 + 묶음 넷) · 전체 보기의 표 넷.
- 판단 지침 한 글(자리 연결 — #judgment/merge:links): 읽는 에이전트(작업 번호 · 이름 → /agents#…) · 쓰이는 워크플로우 › 단계 · 글 · 노트 아이콘 뒤의 설명.
- 고치기(헤딩 지침 「규칙식 제안」): 「고치기」 → 저장 → 「고친 본」 · 목차의 「고침」 → 「기본본과 견주기」(더한 줄 +) → 「기본으로 되돌리기」.
- 양식별(연차보고서): 절 다섯(양식 정보 · 양식 지침 · 규정 · 테마 · 프로젝트의 문서 목적) · 양식 지침의 나무(「모든 자리 보기」) · 규정 목록 · 규정 YAML 을 고쳐 저장(틀린 글은 400 — 알림만) → 목록이 따라옴.
- 좁은 폭(800px): 가로 넘침 없음. 콘솔 오류 없음(일부러 낸 400 은 뺌).

    python -X utf8 tools/smoke_guides_page_ui.py <출력 폴더> [--port 18449]
"""
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
ap.add_argument("--port", type=int, default=18449)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
(tmp / "forms").mkdir(parents=True, exist_ok=True)
for src in (ROOT / "forms").glob("*"):   # 저장소 forms/ 의 사본(양식 정보 md · 양식 지침 YAML) — 시험이 저장소 파일을 고치지 않게
    if src.suffix in (".md", ".yaml"):
        shutil.copy2(src, tmp / "forms" / src.name)
FORM = "연차보고서"
RULES = ("form: 연차보고서\nrules:\n  - id: r1\n    text: 본문은 10쪽 이내로 쓴다.\n    source: {name: 작성지침서, clause: 3항}\n    required: true\n")
(tmp / "forms" / f"{FORM}.rules.yaml").write_text(RULES, encoding="utf-8")
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"),
       "NFM_AGENT_PROMPTS": str(tmp / "agent_prompts"), "NFM_AGENT_NOTES": str(tmp / "agent_notes.json"), "NFM_FORM_THEMES": str(tmp / "form_themes"), "NFM_TOOL_NAMES": str(tmp / "tool_names.json"),
       "NFM_STEP_TEXTS": str(tmp / "step_texts.json"), "NFM_TASKS": str(tmp / "tasks.json"), "NFM_REQS": str(tmp / "requirements.json"), "NFM_DOCLIB_URL": "http://127.0.0.1:9", "PYTHONUTF8": "1"}
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL", "NFM_AUTH", "NFM_MERGE_GUIDES"):
    env.pop(k, None)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:700] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def wait_server(timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if requests.get(base + "/api/headings/llm", timeout=2).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.4)
    raise SystemExit("서버가 안 뜸")


def watch(pg):
    pg.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
    pg.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
    pg.on("dialog", lambda d: d.accept())


TAG = "() => [...document.querySelectorAll('#gpMain .gp-title .gp-tag')].map((e) => e.textContent)"


def main():
    wait_server()
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1500, "height": 1000}, device_scale_factor=1)
        page = ctx.new_page()
        watch(page)
        # 입구 — 에이전트 창 머리의 톱니 옆
        page.goto(base)
        page.wait_for_selector("#agentBtn")
        page.click("#agentBtn")
        page.wait_for_selector("#agentFloat:not([hidden]) #agentGuides")
        g = page.evaluate("() => { const a = document.getElementById('agentGuides'); return [a.getAttribute('href'), a.target, a.getAttribute('aria-label'), a.previousElementSibling.id, !!a.querySelector('svg')]; }")
        check("에이전트 창 머리 — 톱니 바로 옆 「지침 설정」(/guides · 새 탭 · 아이콘)", g == ["/guides", "_blank", "지침 설정", "agentSettings", True], g)
        # 페이지
        page.goto(base + "/guides")
        page.wait_for_selector("#gpNav a")
        page.wait_for_selector("#gpMain .gp-table")
        v = page.evaluate("""() => ({ title: document.querySelector('.ags-title').textContent, tabs: [...document.querySelectorAll('.gp-tab')].map((e) => [e.textContent, e.classList.contains('is-on')]),
          scripts: [...document.scripts].map((s) => new URL(s.src).pathname), nav: document.querySelectorAll('#gpNav a').length, groups: [...document.querySelectorAll('#gpNav h2')].length,
          tables: document.querySelectorAll('#gpMain .gp-table').length, note: document.getElementById('gpNote').textContent, appjs: typeof state })""")
        check("상단 줄 — 제목 · 탭 둘(판단 지침이 먼저) · 글 수", v["title"] == "지침 설정" and v["tabs"] == [["판단 지침", True], ["양식별", False]] and v["note"].startswith("글 "), v)
        check("account/chip.js 가 먼저 · app.js 를 읽지 않음", v["scripts"][0] == "/static/account/chip.js" and v["scripts"][-1] == "/static/guides.js" and v["appjs"] == "undefined", v["scripts"])
        check("목차(전체 보기 + 묶음 넷 · 글 스물 넘게) · 전체 보기의 표 넷", v["groups"] == 4 and v["nav"] >= 20 and v["tables"] == 4, v)
        page.screenshot(path=str(OUT / "01_judgment.png"))
        # 한 글 — 읽는 에이전트 · 쓰이는 곳
        page.click('#gpNav a[href="#judgment/merge%3Alinks"]')
        page.wait_for_selector("#gpMain .gp-reader")
        r = page.evaluate("""() => ({ agent: [...document.querySelectorAll('.gp-agent')].map((a) => [a.textContent, a.getAttribute('href')]), used: [...document.querySelectorAll('.gp-used li')].map((e) => e.textContent),
          text: document.querySelector('.gp-text').textContent.length, cur: document.querySelector('#gpNav a[aria-current="true"]').textContent, tag: document.querySelector('.gp-title .gp-tag').textContent })""")
        check("자리 연결 — 읽는 에이전트(작업 번호 · 이름 → /agents#merge_links) · 쓰이는 워크플로우 › 단계 · 글 · 「기본본」",
              len(r["agent"]) == 1 and r["agent"][0][0].endswith("자리 연결 검토") and r["agent"][0][1] == "/agents#merge_links" and any("이관" in u and "›" in u for u in r["used"]) and r["text"] > 200 and r["tag"] == "기본본", r)
        page.click("#gpMain .gp-title .gp-help-btn")
        check("설명 문단은 제목 옆 노트 아이콘 뒤에(누르면 펴짐)", page.evaluate("() => { const p = document.querySelector('#gpMain .gp-title .gp-help-pop'); return !p.hidden && p.textContent.length > 40 && !document.querySelector('#gpMain > p.ags-help'); }"))
        # 고치기 → 견주기 → 기본으로
        page.goto(base + "/guides#judgment/heading%3Arules")
        page.wait_for_selector("#gpMain .gp-text")
        page.click("#gpMain button:has-text('고치기')")
        ta = page.locator("#gpMain textarea.gp-ta")
        ta.fill(ta.input_value().rstrip() + "\n- 화면 검사가 더한 줄")   # 글 끝의 줄바꿈을 걷고 붙인다(안 걷으면 빈 줄 하나가 더한 줄로 함께 셈된다)
        page.click("#gpMain button:has-text('저장')")
        page.wait_for_function("() => [...document.querySelectorAll('#gpMain .gp-title .gp-tag')].some((e) => e.textContent.startsWith('고친 본'))")
        check("헤딩 지침을 고쳐 저장 → 「고친 본 · 내 사본」 · 목차에 「고침」", page.evaluate("() => document.querySelector('#gpNav a[aria-current=\"true\"] .gp-tag').textContent") == "고침", page.evaluate(TAG))
        page.click("#gpMain button:has-text('기본본과 견주기')")
        page.wait_for_selector("#gpMain .gp-diff")
        d = page.evaluate("() => ({ add: [...document.querySelectorAll('.gp-dl.is-add')].map((e) => e.textContent.trim()), del: document.querySelectorAll('.gp-dl.is-del').length, cap: document.querySelector('.gp-diff-cap').textContent })")
        check("기본본과 견주기 — 더한 줄(+) 하나 · 빠진 줄 없음 · 무엇과 무엇을 견주는지 적음", d["add"] == ["+ - 화면 검사가 더한 줄"] and d["del"] == 0 and d["cap"].startswith("기본본 → 고친 본"), d)
        page.screenshot(path=str(OUT / "02_diff.png"))
        page.click("#gpMain button:has-text('기본으로 되돌리기')")
        page.wait_for_function("() => { const t = document.querySelector('#gpMain .gp-title .gp-tag'); return t && t.textContent === '기본본'; }")
        check("기본으로 되돌리기 → 「기본본」 · 견주기 단추 없음", page.locator("#gpMain button:has-text('기본본과 견주기')").count() == 0)
        # 양식별
        page.click("#gpTabForms")
        page.wait_for_selector(f'#gpNav a[href="#forms/{requests.utils.quote(FORM)}"]')
        check("양식별 — 전체 보기의 표에 양식마다 한 줄", page.locator("#gpMain .gp-table tr").count() >= 2)
        page.click(f'#gpNav a[href="#forms/{requests.utils.quote(FORM)}"]')
        page.wait_for_selector("#gpMain .gp-rules li")
        f = page.evaluate("""() => ({ secs: [...document.querySelectorAll('#gpMain section.gp-sec > h3')].map((h) => h.firstChild.textContent.replace(/\\s*\\d+$/, '')), rules: [...document.querySelectorAll('.gp-rules li')].map((li) => li.textContent),
          tag: document.querySelector('.gp-rules .gp-tag').textContent })""")
        check("양식 하나 — 절 다섯(양식 정보 · 양식 지침 · 규정 · 테마 · 프로젝트의 문서 목적) · 규정 줄(필수 · 출처 · 문서 전체)",
              f["secs"] == ["양식 정보", "양식 지침", "규정", "테마", "프로젝트의 문서 목적"] and len(f["rules"]) == 1 and f["tag"] == "필수" and "작성지침서 3항" in f["rules"][0] and "문서 전체" in f["rules"][0], f)
        before = page.locator("#gpMain .gp-node-section").count()
        page.click("#gpMain button:has-text('모든 자리 보기')")
        check("양식 지침의 나무 — 「모든 자리 보기」 로 절 › 표의 구조가 펴짐", page.locator("#gpMain .gp-node-section").count() > before and page.locator("#gpMain .gp-node-table").count() > 0, before)
        page.screenshot(path=str(OUT / "03_form.png"))
        sec = page.locator("#gpFormRules")
        sec.locator("button:has-text('YAML 보기 · 고치기')").click()
        ta = sec.locator("textarea.gp-ta")
        ta.wait_for()
        ta.fill("rules: 글")
        sec.locator("button:has-text('저장')").click()
        page.wait_for_selector("#gpToast.err:not([hidden])")
        check("틀린 YAML 은 저장하지 않고 알림(글 칸은 그대로)", ta.input_value() == "rules: 글" and "목록" in page.inner_text("#gpToast"), page.inner_text("#gpToast"))
        ta.fill(RULES + "  - id: r2\n    text: 표의 수치는 단위와 함께 적는다.\n    required: false\n")
        sec.locator("button:has-text('저장')").click()
        page.wait_for_function("() => document.querySelectorAll('#gpMain .gp-rules li').length === 2")
        check("규정 YAML 을 고쳐 저장 → 목록이 따라옴(필수 · 권고)", page.evaluate("() => [...document.querySelectorAll('.gp-rules .gp-tag')].map((e) => e.textContent)") == ["필수", "권고"])
        # 좁은 폭
        page.set_viewport_size({"width": 800, "height": 900})
        page.wait_for_timeout(200)
        w = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
        check("800px — 가로 넘침 없음", w[0] <= w[1], w)
        page.screenshot(path=str(OUT / "04_narrow.png"))
        b.close()
    real = [e for e in errors if "400" not in e]
    check("콘솔 오류 없음", not real, real[:5])


try:
    main()
finally:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'OK' if not fails else 'FAIL'} — 실패 {len(fails)}" + (f": {fails}" if fails else ""))
sys.exit(1 if fails else 0)
