"""그림 도구(spec_그림 — app/static/pic_tools.js · app/pic_tools_api.py) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. LLM 이 그림을 읽는 두 끝점(read-table · read-caption)만 흉내 내고 나머지 끝점은 진짜.

연구개발계획서 양식에 그림 넷을 넣은 문서(tests/test_pic_tools.py 의 _made — 본문 A · B · C · 표 t996 칸 안 D)를 올린다.

 1. 그림을 누르면 파란 테두리 + 그림 위의 띠 「그림 | 표로 바꾸기 · 캡션 넣기 · 선명하게 · 가운데」 · 띠는 그림 바로 위 · 화면 안.
 2. Ctrl+누름으로 둘째 그림 → 띠 「그림 둘 | 한 줄에 · 가운데」 → 「한 줄에」 → 두 그림이 한 문단(서버) · 화면에서 한 줄(같은 위쪽).
 3. 「선명하게」 → 2열 「선명하게」: 지금 · 바꾼 뒤 그림(화소 n×n → m×m) · 「바꾸기」 → 서버의 그림 파일이 바뀜 · 표시 크기 그대로.
 4. 「캡션 넣기」 → 2열: 「캡션 짓기(LLM)」 → 입력 칸에 지은 캡션 → 「넣기」 → 그림 아래 캡션 문단 · 띠의 「캡션 넣기」 가 흐려짐(이미 캡션).
 5. 오른쪽 단추 → 메뉴에 같은 항목 → 「표로 바꾸기」 → 2열: 표 양식(기본 = 가까운 표) · 「그림 읽기(LLM)」 → 격자(칸 고침 가능) · 캡션 · 「문서에 넣기」 → 표가 들어가고 그림은 없어짐 · 고친 칸 글 그대로 · 캡션은 표 위.
 6. Esc 로 고르기 풀림 · 띠 없어짐 · 콘솔 오류 없음.

    python -X utf8 tools/smoke_pics_ui.py <출력 폴더> [--port 18520]
"""
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
sys.path.insert(0, str(ROOT))
from tests.test_pic_tools import _made  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--port", type=int, default=18520)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "PYTHONUTF8": "1"}
env.setdefault("NFM_TASKS", str(tmp / "tasks.json"))
env.setdefault("NFM_AGENT_NOTES", str(tmp / "agent_notes.json"))
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []
COL = "#headsDlgBody"
GRID = {"headerRows": 0, "headerCols": 1, "footRows": 0, "rows": [{"cells": [{"text": "Ship ID", "rowSpan": 1, "colSpan": 1}, {"text": "imo1234567", "rowSpan": 1, "colSpan": 1}]},
                                                                  {"cells": [{"text": "Short ID", "rowSpan": 1, "colSpan": 1}, {"text": "0001", "rowSpan": 1, "colSpan": 1}]}]}


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


def doc_blocks(doc):
    return requests.get(f"{base}/api/docs/{doc}", timeout=120).json()["blocks"]


def walk(blocks):
    for b in blocks:
        yield b
        for c in b.get("cells") or []:
            yield from walk(c.get("blocks") or [])


def info(doc, pid):
    return requests.get(f"{base}/api/docs/{doc}/pics/{pid}", timeout=60)


BAR = """() => { const b = document.querySelector('.pic-bar'); if (!b || b.hidden) return null; const r = b.getBoundingClientRect();
  return { name: b.querySelector('.pic-bar-name').textContent, btns: [...b.querySelectorAll('button')].map((x) => ({ t: x.textContent, off: x.disabled })), top: r.top, bottom: r.bottom, left: r.left, right: r.right, vis: getComputedStyle(b).visibility }; }"""
RECT = """(id) => { const n = document.querySelector(`#doc [data-img="${id}"]`); if (!n) return null; const r = n.getBoundingClientRect(); return { top: r.top, left: r.left, bottom: r.bottom, outline: getComputedStyle(n).outlineStyle }; }"""


def click_bar(page, name):
    page.locator(".pic-bar button", has_text=name).first.click()


def main():
    wait_server()
    data, _ = _made()
    r = requests.post(base + "/api/docs", files={"file": ("그림_넷.hwpx", data, "application/octet-stream")}, timeout=120)
    assert r.status_code == 200, r.text
    doc = r.json()["docId"]
    pics = [b["id"] for b in walk(doc_blocks(doc)) if b.get("type") == "image" and (b.get("media") or "").endswith(".png")]
    pics.sort(key=lambda i: info(doc, i).json()["cell"])
    a, b, c, d = pics
    print(f"INFO 그림 A {a} · B {b} · C {c} · 칸 안 D {d}", flush=True)

    with sync_playwright() as p:
        br = p.chromium.launch()
        page = br.new_page(viewport={"width": 1600, "height": 950}, device_scale_factor=1)
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda dl: dl.accept())
        page.route(re.compile(r".*/pics/[^/]+/read-caption$"), lambda route: route.fulfill(status=200, content_type="application/json",
                   body=json.dumps({"caption": "< 최종목표 개념도 >", "note": "소속 헤딩 「2-1. 최종목표」 에서", "call": {"model": "m", "ms": 900, "costUsd": 0.01}, "context": {}, "rev": 0})))
        page.route(re.compile(r".*/pics/[^/]+/read-table$"), lambda route: route.fulfill(status=200, content_type="application/json",
                   body=json.dumps({"tables": [GRID], "caption": ["1.4 Data Channel ID 의 예시", "아래 예시에서 …"], "note": "표 하나", "dropped": [], "call": {"model": "m", "ms": 1200, "costUsd": 0.02},
                                    "template": "t996", "context": {}, "rev": 0})))
        page.goto(f"{base}/#w={doc}")
        page.wait_for_selector(f'#doc img.img[data-img="{a}"]', timeout=60000)

        # 1. 고르기 · 띠
        page.locator(f'#doc [data-img="{a}"]').scroll_into_view_if_needed()
        page.locator(f'#doc [data-img="{a}"]').click()
        page.wait_for_function("() => { const b = document.querySelector('.pic-bar'); return b && !b.hidden; }", timeout=10000)
        bar, rect = page.evaluate(BAR), page.evaluate(RECT, a)
        check("1. 그림을 누르면 파란 테두리 + 띠 「그림 | 표로 바꾸기 · 캡션 넣기 · 선명하게 · 가운데」 — 그림 바로 위 · 화면 안",
              bar and bar["name"] == "그림" and [x["t"] for x in bar["btns"]] == ["표로 바꾸기", "캡션 넣기", "선명하게", "가운데"] and not any(x["off"] for x in bar["btns"])
              and rect["outline"] == "solid" and bar["bottom"] <= rect["top"] + 1 and bar["top"] >= 0 and bar["right"] <= 1600 and bar["vis"] != "hidden", [bar, rect])
        page.screenshot(path=str(OUT / "01_bar.png"))

        # 2. 둘째 그림 → 한 줄에
        page.locator(f'#doc [data-img="{b}"]').scroll_into_view_if_needed()
        page.locator(f'#doc [data-img="{b}"]').click()
        page.locator(f'#doc [data-img="{c}"]').scroll_into_view_if_needed()
        page.locator(f'#doc [data-img="{c}"]').click(modifiers=["Control"])
        bar = page.evaluate(BAR)
        check("2a. Ctrl+누름 → 띠 「그림 둘 | 한 줄에 · 가운데」", bar and bar["name"] == "그림 둘" and [x["t"] for x in bar["btns"]] == ["한 줄에", "가운데"], bar)
        click_bar(page, "한 줄에")
        page.wait_for_function("([b, c]) => { const x = document.querySelector(`#doc [data-img=\"${b}\"]`), y = document.querySelector(`#doc [data-img=\"${c}\"]`); "
                               "return x && y && Math.abs(x.getBoundingClientRect().top - y.getBoundingClientRect().top) < 2; }", arg=[b, c], timeout=20000)
        ib, ic = info(doc, b).json(), info(doc, c).json()
        rb, rc = page.evaluate(RECT, b), page.evaluate(RECT, c)
        check("2b. 「한 줄에」 → 두 그림이 한 문단(서버) · 화면에서 같은 위쪽 · 가운데", ib["host"] == ic["host"] and ib["align"] == "center" and abs(rb["top"] - rc["top"]) < 2 and rc["left"] > rb["left"], [ib, ic, rb, rc])
        page.screenshot(path=str(OUT / "02_row.png"))

        # 3. 선명하게
        page.keyboard.press("Escape")
        page.locator(f'#doc [data-img="{a}"]').scroll_into_view_if_needed()
        page.locator(f'#doc [data-img="{a}"]').click()
        before = info(doc, a).json()
        click_bar(page, "선명하게")
        page.wait_for_function("() => [...document.querySelectorAll('#headsDlgBody .pic-two-fig figcaption')].some((f) => f.textContent.includes('→'))", timeout=30000)
        caps = page.evaluate("() => [...document.querySelectorAll('#headsDlgBody .pic-two-fig figcaption')].map((f) => f.textContent)")
        check("3a. 2열 「선명하게」 — 지금 · 바꾼 뒤(화소 400×200 → m×m)", page.evaluate("() => document.getElementById('headsDlgTitle').textContent") == "선명하게"
              and caps[0] == "지금" and "400×200 →" in caps[1], caps)
        page.screenshot(path=str(OUT / "03_sharpen.png"))
        page.locator("#headsDlgFoot button", has_text="바꾸기").click()
        page.wait_for_function("(m) => { const t = document.getElementById('toast'); return t && !t.hidden && t.textContent.includes('또렷하게'); }", arg=before["media"], timeout=30000)
        after = info(doc, a).json()
        check("3b. 「바꾸기」 → 서버의 그림 파일이 바뀜 · 표시 크기 그대로", after["media"] != before["media"] and (after["widthMm"], after["heightMm"]) == (before["widthMm"], before["heightMm"]), [before, after])

        # 4. 캡션 넣기
        page.locator(f'#doc [data-img="{b}"]').scroll_into_view_if_needed()
        page.locator(f'#doc [data-img="{b}"]').click()
        click_bar(page, "캡션 넣기")
        page.wait_for_selector("#headsDlgFoot button:has-text('캡션 짓기(LLM)')", timeout=10000)
        page.locator("#headsDlgFoot button", has_text="캡션 짓기(LLM)").click()
        page.wait_for_function("() => (document.querySelector('#headsDlgBody .pic-col-capone') || {}).value === '< 최종목표 개념도 >'", timeout=10000)
        page.locator("#headsDlgFoot button", has_text="넣기").first.click()
        page.wait_for_function("(t) => [...document.querySelectorAll('#doc .para')].some((p) => p.textContent.trim() === t)", arg="< 최종목표 개념도 >", timeout=20000)
        page.locator(f'#doc [data-img="{b}"]').click()
        bar = page.evaluate(BAR)
        cap_btn = next((x for x in (bar or {}).get("btns", []) if x["t"] == "캡션 넣기"), None)
        check("4. 「캡션 짓기(LLM)」 → 입력 칸 · 「넣기」 → 그림 아래 캡션 문단 · 띠의 「캡션 넣기」 흐림", info(doc, b).json()["hasCaption"] and cap_btn and cap_btn["off"], bar)
        page.screenshot(path=str(OUT / "04_caption.png"))

        # 5. 오른쪽 단추 → 표로 바꾸기
        page.locator(f'#doc [data-img="{a}"]').scroll_into_view_if_needed()
        page.locator(f'#doc [data-img="{a}"]').click(button="right")
        menu = page.evaluate("() => { const m = document.querySelector('.ctx-menu'); return m && !m.hidden ? [...m.querySelectorAll('button')].map((x) => x.textContent) : null; }")
        check("5a. 오른쪽 단추 메뉴 — 같은 항목", menu == ["표로 바꾸기", "캡션 넣기", "선명하게", "가운데"], menu)
        page.locator(".ctx-menu button", has_text="표로 바꾸기").click()
        page.wait_for_selector("#headsDlgFoot button:has-text('그림 읽기(LLM)')", timeout=10000)
        page.wait_for_function("() => (document.querySelector('#headsDlgBody .pic-col-tpl') || {}).value", timeout=10000)   # 그림 정보(표 양식 기본)가 온 뒤
        tpl = page.evaluate("() => document.querySelector('#headsDlgBody .pic-col-tpl').value")
        page.locator("#headsDlgFoot button", has_text="그림 읽기(LLM)").click()
        page.wait_for_selector("#headsDlgBody table.pic-grid td", timeout=10000)
        cell = page.locator("#headsDlgBody table.pic-grid td").nth(1)
        cell.click()
        page.keyboard.press("End")
        page.keyboard.type("9")
        page.screenshot(path=str(OUT / "05_table.png"))
        page.locator("#headsDlgFoot button", has_text="문서에 넣기").click()
        page.wait_for_function("(a) => !document.querySelector(`#doc [data-img=\"${a}\"]`) && [...document.querySelectorAll('#doc table.tbl td')].some((t) => t.textContent.includes('00019'))", arg=a, timeout=30000)
        bl = list(walk(doc_blocks(doc)))
        new = next((x for x in bl if x.get("type") == "table" and any((cc.get("text") or "") == "00019" for cc in x.get("cells") or [])), None)
        capt = [x.get("text") for x in bl if new and x.get("captionOf") == new["id"]]
        check("5b. 표 양식 기본 = t996 · 「문서에 넣기」 → 표(고친 칸 글 그대로) · 그림 없어짐 · 캡션 두 줄",
              tpl == "t996" and new is not None and not any(x.get("id") == a for x in bl) and capt == ["1.4 Data Channel ID 의 예시", "아래 예시에서 …"], [tpl, capt])
        page.screenshot(path=str(OUT / "06_table_in.png"))

        # 6. Esc
        page.locator(f'#doc [data-img="{c}"]').scroll_into_view_if_needed()
        page.locator(f'#doc [data-img="{c}"]').click()
        page.keyboard.press("Escape")
        check("6. Esc → 고르기 풀림 · 띠 없어짐", page.evaluate(BAR) is None and page.evaluate(RECT, c)["outline"] != "solid")
        br.close()
    check("콘솔 오류 없음", not errors, errors[:5])


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
