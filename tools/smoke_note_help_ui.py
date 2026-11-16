"""설명 노트: 실제 시작 화면과 공용 도움말의 마우스·키보드·좁은 화면·dialog 동작.

python -X utf8 tools/smoke_note_help_ui.py <그림·기록 폴더> [--port 18179]
임시 데이터의 서버를 띄우고 끝에 닫는다. 사용자 문서나 8114 서버는 쓰지 않는다.
"""
import argparse
import os
import subprocess
import sys
import tempfile
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
OUT.mkdir(parents=True, exist_ok=True)
fails, errors = [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:400] if detail else ""), flush=True)
    if not ok:
        fails.append(name)


def resize(page, width, height):
    # set_viewport_size 완료와 브라우저 resize 사건 처리는 별개다. 사건을 먼저 기다릴 준비를 한다.
    page.evaluate("""() => {
        window.noteHelpResized = false;
        window.addEventListener('resize', () => { window.noteHelpResized = true; }, {once: true});
    }""")
    page.set_viewport_size({"width": width, "height": height})
    page.wait_for_function("window.noteHelpResized === true", timeout=5000)


with tempfile.TemporaryDirectory(prefix="note-help-", dir=OUT) as tmp:
    env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "PYTHONUTF8": "1"}
    for key, name in (("NFM_WORKS", "works"), ("NFM_RENDER", "render"), ("NFM_HEADINGS", "headings"), ("NFM_FORMS", "forms"), ("NFM_DIVISION_PRESETS", "presets.json")):
        env[key] = str(Path(tmp) / name)
    with (OUT / "server.log").open("w", encoding="utf-8") as log:
        proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        base = f"http://127.0.0.1:{args.port}"
        try:
            for _ in range(300):
                try:
                    if requests.get(base + "/api/status", timeout=1).ok:
                        break
                except requests.RequestException:
                    time.sleep(.2)
            else:
                raise RuntimeError("임시 서버 시작 실패")
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(base)
                note = page.get_by_role("button", name="TASK 시작 안내", exact=True)
                note.wait_for()
                check("고정 설명은 노트 아이콘 · 중첩 단추 없음", page.locator("[data-note] > .panel-help").count() == 7 and page.locator("button button").count() == 0)
                note.hover()
                tip = page.locator("#panelHelpTooltip")
                check("마우스 올림으로 설명 · 접근성 연결", tip.is_visible() and "목적 문서를 고른 뒤 TASK를 누르세요" in tip.inner_text() and note.get_attribute("aria-describedby") == "panelHelpTooltip")
                tip.hover()
                page.wait_for_timeout(220)
                check("설명 위로 마우스를 옮겨도 유지", tip.is_visible())
                page.mouse.move(1, 1)
                page.wait_for_timeout(220)
                check("마우스 벗어나면 닫힘", not tip.is_visible())
                note.evaluate("b => b.setAttribute('aria-describedby', 'homeTasksTitle')")
                note.focus()
                check("키보드 초점으로 설명 · 기존 설명 관계 유지", tip.is_visible() and set(note.get_attribute("aria-describedby").split()) == {"homeTasksTitle", "panelHelpTooltip"})
                page.keyboard.press("Escape")
                check("Escape 닫기 · 초점/기존 설명 유지", not tip.is_visible() and note.get_attribute("aria-describedby") == "homeTasksTitle" and note.evaluate("b => b === document.activeElement"))
                note.click()
                page.mouse.move(1, 1)
                page.wait_for_timeout(220)
                check("클릭해 고정한 설명 유지", tip.is_visible())
                note.click()
                check("다시 누르면 닫힘", not tip.is_visible())
                note.click()
                page.locator("#homeTasksTitle").click()
                check("밖을 누르면 닫힘", not tip.is_visible())
                page.evaluate("""() => {
                    const d = document.createElement('details'); d.id = 'noteTestDetails';
                    d.style.cssText = 'position:fixed;left:12px;top:12px;z-index:9999;background:white';
                    const s = document.createElement('summary'); s.textContent = '세부 단계';
                    const b = hHelp('단계 노트 검사', '도움말만 열고 단계는 펼치지 않습니다.');
                    s.append(b); d.append(s); document.body.append(d);
                }""")
                page.get_by_role("button", name="단계 노트 검사", exact=True).click()
                check("summary 안 노트는 단계 펼침을 바꾸지 않음", not page.locator("#noteTestDetails").evaluate("d => d.open") and tip.is_visible())
                page.evaluate("() => { panelHelpClose(); document.getElementById('noteTestDetails').remove(); }")
                resize(page, 320, 480)
                page.evaluate("""() => {
                    const b = hHelp('경계 검사', '긴 설명 '.repeat(150)); b.id = 'edgeNote';
                    b.style.cssText = 'position:fixed;right:0;bottom:0;z-index:9999'; document.body.append(b);
                }""")
                page.locator("#edgeNote").focus()
                bounds = tip.evaluate("e => { const b = e.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom, e.scrollHeight > e.clientHeight]; }")
                check("320px 화면 모서리에서도 안 잘림 · 긴 설명 스크롤", bounds[0] >= 9 and bounds[1] >= 9 and bounds[2] <= 311 and bounds[3] <= 471 and bounds[4], bounds)
                page.screenshot(path=str(OUT / "note-narrow.png"))
                resize(page, 1440, 900)
                tip.wait_for(state="hidden", timeout=5000)
                check("화면 크기 변경 시 닫힘", not tip.is_visible())
                page.evaluate("() => { document.getElementById('edgeNote').remove(); document.getElementById('worksDlg').showModal(); }")
                dialog_note = page.get_by_role("button", name="작업 목록 안내", exact=True)
                dialog_note.hover()
                check("dialog 위에서도 설명 표시", tip.is_visible() and tip.evaluate("e => { const r=e.getBoundingClientRect(); return document.elementFromPoint(r.left+15,r.top+15)===e; }"))
                tip.hover()
                page.wait_for_timeout(220)
                check("dialog 설명도 마우스를 옮겨 읽을 수 있음", tip.is_visible())
                page.keyboard.press("Escape")
                check("설명 Escape가 dialog까지 닫지 않음", not tip.is_visible() and page.locator("#worksDlg").evaluate("d => d.open"))
                page.evaluate("() => document.getElementById('worksDlg').close()")
                page.screenshot(path=str(OUT / "home-notes.png"))
                check("브라우저 오류 없음", not errors, errors)
                browser.close()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

print("ALL PASS" if not fails else "FAIL " + ", ".join(fails))
sys.exit(1 if fails else 0)
