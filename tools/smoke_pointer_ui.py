"""포인터(spec_포인터 ② §1~§3 · §6 「시작 화면」) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright 브라우저 둘(창 크기가 다름).

    python -X utf8 tools/smoke_pointer_ui.py <그림·임시 폴더> [--port 18172]

① 시작 화면(2026-11-23 사용자 "첫페이지 부터 포인터 기능 넣어줘"): 두 화면 모두 문서를 열지 않은 채 — 상단 바에 「포인터」 단추 · 방 "home" 에 붙음 ·
   A 가 켜고 워크플로우 카드 위에서 움직이면 B 에 A 의 포인터(이름표)가 **B 의 같은 카드의 같은 비율 자리**에(창 폭이 달라 카드 자리가 다르다) · 누르면 B 에 「클릭」 ·
   시작 화면 밖(상단 바)으로 나가면 B 에서 걷힘.
② 문서로 가면 방이 바뀐다: A 가 문서를 열면 B(시작 화면)의 「같이 보는 화면」 에서 빠지고, B 도 같은 문서를 열면 A 의 포인터가 같은 문단의 같은 비율 자리에(전의 문서 포인터 그대로).
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
ap.add_argument("--port", type=int, default=18172)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_TASKS": str(tmp / "tasks.json"),
       "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:300] if detail != "" else ""), flush=True)
    if not ok:
        fails.append(name)


# 남의 포인터(이름표 · 화살표 끝 자리) · 같이 보는 화면 수 · 방 · 「클릭」 표시
SEEN = """() => { const c = [...document.querySelectorAll('#ptrLayer .ptr-cur')].find((x) => !x.hidden), b = document.getElementById('pointerBtn'), vis = (e) => !!e && e.getClientRects().length > 0;
  const m = c ? (c.style.transform.match(/translate\\((-?[\\d.]+)px, (-?[\\d.]+)px\\)/) || []) : [];
  return { cur: c ? { x: +m[1], y: +m[2], name: c.textContent, edge: c.classList.contains('up') || c.classList.contains('down') } : null, room: ptr.doc, live: ptrLive(), n: ptr.peers.size,
           btn: vis(b), pressed: b && b.getAttribute('aria-pressed'), clicks: document.querySelectorAll('#ptrLayer .ptr-click').length }; }"""


def center(page, sel, fx=.5, fy=.5):
    r = page.locator(sel).first.bounding_box()
    return r["x"] + r["width"] * fx, r["y"] + r["height"] * fy


def near(a, b, tol=3):
    return a is not None and b is not None and abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


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
        ca, cb = browser.new_context(viewport={"width": 1500, "height": 950}), browser.new_context(viewport={"width": 1100, "height": 820})
        A, B = ca.new_page(), cb.new_page()
        for name, pg in (("A", A), ("B", B)):
            pg.on("pageerror", lambda e, n=name: errors.append(f"{n} pageerror: {e}"))
            pg.on("console", lambda m, n=name: errors.append(f"{n} console: {m.text}") if m.type == "error" else None)
            pg.goto(base)
            pg.evaluate("() => { try { localStorage.removeItem('nfm.pointer'); localStorage.removeItem('nfm.pointerName'); } catch {} }")
            pg.reload()
        for pg in (A, B):
            pg.wait_for_function("() => document.body.classList.contains('no-doc') && typeof ptrLive === 'function' && ptrLive() && document.querySelector('#taskCards [data-task]')", timeout=60000)
        A.wait_for_function("() => ptr.peers.size === 1", timeout=20000)
        a0, b0 = A.evaluate(SEEN), B.evaluate(SEEN)
        check("① 시작 화면 — 두 화면 모두 상단 바에 「포인터」 단추 · 방 home · 서로 같이 보는 화면 1 · 처음엔 꺼짐",
              a0["btn"] and b0["btn"] and a0["room"] == b0["room"] == "home" and a0["n"] == b0["n"] == 1 and a0["pressed"] == "false", (a0, b0))
        A.screenshot(path=str(OUT / "1_home_A.png"), clip={"x": 0, "y": 0, "width": 1500, "height": 120})

        # 켜고 워크플로우 카드 위에서 — B 의 같은 카드 · 같은 비율 자리에
        A.click("#pointerBtn")
        A.wait_for_function("() => ptr.on && document.getElementById('pointerBtn').getAttribute('aria-pressed') === 'true'")
        card = '#taskCards [data-task="plan_to_report"]'
        B.locator(card).scroll_into_view_if_needed()
        x, y = center(A, card, .3, .6)
        A.mouse.move(x - 40, y)
        A.mouse.move(x, y, steps=4)
        B.wait_for_function("() => [...document.querySelectorAll('#ptrLayer .ptr-cur')].some((c) => !c.hidden)", timeout=10000)
        B.wait_for_timeout(300)
        bs, want = B.evaluate(SEEN), center(B, card, .3, .6)
        ab, bb = A.locator(card).bounding_box(), B.locator(card).bounding_box()
        check("① A 가 켜고 워크플로우 카드(이관) 위에서 움직임 → B 에 A 의 포인터(이름표 「사용자 N」) · B 의 같은 카드의 같은 비율 자리(창 폭이 달라 카드 자리가 다름)",
              bs["cur"] is not None and not bs["cur"]["edge"] and bs["cur"]["name"].startswith("사용자") and near((bs["cur"]["x"], bs["cur"]["y"]), want)
              and (round(ab["x"]), round(ab["width"])) != (round(bb["x"]), round(bb["width"])), {"B": bs["cur"], "want": want, "cardA": ab, "cardB": bb})
        B.screenshot(path=str(OUT / "2_home_B_sees.png"))

        # 누름 — 아무 일도 하지 않는 제목(「워크플로우」)을 눌러 「클릭」
        hx, hy = center(A, "#homeTasksTitle")
        A.mouse.move(hx, hy, steps=3)
        A.mouse.down()
        A.mouse.up()
        B.wait_for_function("() => document.querySelectorAll('#ptrLayer .ptr-click').length > 0", timeout=5000)
        bc = B.evaluate("""() => { const c = document.querySelector('#ptrLayer .ptr-click'); return c ? { x: parseFloat(c.style.left), y: parseFloat(c.style.top), text: c.textContent } : null; }""")
        check("① A 가 누름 → B 의 같은 자리(제목 「워크플로우」)에 「클릭」", bc is not None and bc["text"] == "클릭" and near((bc["x"], bc["y"]), center(B, "#homeTasksTitle"), 4), (bc, center(B, "#homeTasksTitle")))

        # 표식 없는 여백 → 시작 화면 바탕(id=empty)의 스크롤 내용 안의 비율 · 시작 화면 밖(상단 바)으로 → 걷힘
        A.mouse.move(12, 600, steps=3)
        A.wait_for_timeout(250)
        at = A.evaluate("() => ptrAt(12, 600)")
        check("① 시작 화면의 여백 → 자리 = 시작 화면 바탕(id=empty — 스크롤 내용 안의 비율)", at is not None and at["k"] == "h" and at["a"] == "id=empty", at)
        A.mouse.move(700, 15, steps=4)   # 상단 바 = 시작 화면(#empty) 밖
        B.wait_for_function("() => ![...document.querySelectorAll('#ptrLayer .ptr-cur')].some((c) => !c.hidden)", timeout=5000)
        check("① 시작 화면 밖(상단 바)으로 나가면 B 에서 A 의 포인터가 걷힘", B.evaluate(SEEN)["cur"] is None)

        # ② 문서로 — A 가 문서를 열면 방이 바뀐다(B 의 「같이 보는 화면」 에서 빠짐) · B 도 열면 문서 포인터(전처럼)
        form = ROOT / "samples" / "연구개발계획서_양식.hwpx"
        doc = requests.post(f"{base}/api/docs?new=1", files={"file": (form.name, form.read_bytes())}, timeout=300).json()["docId"]
        A.evaluate("(id) => { location.hash = '#w=' + id; }", doc)
        A.reload()
        A.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') && ptrLive()", arg=doc, timeout=180000)
        B.wait_for_function("() => ptr.peers.size === 0", timeout=20000)
        a2, b2 = A.evaluate(SEEN), B.evaluate(SEEN)
        check("② A 가 문서를 엶 → A 의 방 = 문서 id · B(시작 화면)의 같이 보는 화면 0 · A 의 단추는 그대로 켜짐(이 브라우저에 기억)",
              a2["room"] == doc and b2["room"] == "home" and b2["n"] == 0 and a2["pressed"] == "true", (a2, b2))
        B.evaluate("(id) => { location.hash = '#w=' + id; }", doc)
        B.reload()
        B.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') && ptrLive() && ptr.peers.size === 1", arg=doc, timeout=180000)
        pid = A.evaluate("() => { const ps = [...document.querySelectorAll('#doc .sheet .para[data-id]')].filter((p) => { const r = p.getBoundingClientRect(); return r.width > 200 && r.height > 12 && r.top > 120 && r.bottom < 700; }); return ps[0] ? ps[0].dataset.id : null; }")
        B.evaluate("(id) => document.querySelector(`#doc [data-id=\"${id}\"]`).scrollIntoView({ block: 'center' })", pid)
        sel = f'#doc [data-id="{pid}"]'
        x, y = center(A, sel, .25, .5)
        A.mouse.move(x - 30, y)
        A.mouse.move(x, y, steps=4)
        B.wait_for_function("() => [...document.querySelectorAll('#ptrLayer .ptr-cur')].some((c) => !c.hidden && !c.classList.contains('up') && !c.classList.contains('down'))", timeout=10000)
        B.wait_for_timeout(300)
        bd = B.evaluate(SEEN)
        check("② 같은 문서 — A 의 포인터가 B 의 같은 문단 · 같은 비율 자리에(문서 포인터 그대로)", bd["cur"] is not None and near((bd["cur"]["x"], bd["cur"]["y"]), center(B, sel, .25, .5)), (bd["cur"], center(B, sel, .25, .5)))
        B.screenshot(path=str(OUT / "3_doc_B_sees.png"))
        check("JS 오류 없음", not errors, errors[:5])
        browser.close()
except Exception as e:  # noqa: BLE001
    import traceback
    traceback.print_exc()
    fails.append(f"예외: {e}")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'통과' if not fails else '실패'} — 떨어진 검사 {len(fails)}개" + ("" if not fails else ": " + " / ".join(fails)), flush=True)
sys.exit(1 if fails else 0)
