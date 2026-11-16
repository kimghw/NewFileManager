"""개요 레벨 미리보기·비교 창(spec_hwpx_웹편집 ② §8-3 — app/static/outline_preview.js) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음).

연구개발계획서 양식을 올리고 1·2단계(LLM 없이)를 끝점으로 돌린 뒤 작업을 연다:
- 「템플릿 관계」 T3 L2(서식 3가지)의 「비교」 → 떠 있는 창(모달 아님 · 열과 안 겹침) 「서식 비교」 탭 — 갈래 3줄(대표 먼저) · 다른 항목 열(앞 공백 · 레터 뒤 공백)만 ·
  다른 값 칸 강조 · 견본 글(누르면 문서로) · 「맞추기」 2개 · 「같은 값도 보기」 로 열이 늘어남 · 「대표에 맞추기(2줄)」.
- 가지 템플릿 L2 「o」(p972)의 「자리 수정」 → 창이 「자리 미리보기」 로 — 지금 = 바뀐 뒤(레터 4.2) · 레터 10 을 치면 바뀐 뒤 레터 10.0 · 점선(지금 자리) · 「N줄이 바뀝니다」 ·
  둘째 줄 「직접」 12 → 둘째 줄 12.0 · 창의 「적용」 → 문서가 바뀌고 미리보기는 「바뀌는 줄 없음」 · 실행 취소 → 처음대로 · 너무 작은 레터 위치는 까닭을 보임.
- 「자리 수정」 을 접으면 창이 닫힘 · Esc 로 닫힘 · 머리를 끌어 옮김 · 좁은 창(480px)에서 화면 안 · 콘솔 오류 없음.

    python -X utf8 tools/smoke_outline_preview_ui.py <출력 폴더> [--port 18433]
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
ap.add_argument("--port", type=int, default=18433)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:600] if detail != "" and not ok else ""), flush=True)
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


def run_stage(doc, stage):
    r = requests.post(f"{base}/api/docs/{doc}/headings", json={"stage": stage, "llm": False}, timeout=30)
    assert r.status_code == 202, r.text
    end = time.time() + 300
    while time.time() < end:
        v = requests.get(f"{base}/api/docs/{doc}/headings", timeout=30).json()
        if not v.get("job") or v["job"].get("status") != "running":
            return v
        time.sleep(0.4)
    raise SystemExit("단계가 안 끝남")


WIN = """() => { const w = document.getElementById('olpWin'); if (!w || w.hidden) return null; const r = w.getBoundingClientRect(); const c = document.getElementById('headsDlg').getBoundingClientRect();
  const vals = {}; for (const tr of w.querySelectorAll('.olp-vals tbody tr')) vals[tr.querySelector('th').textContent] = [...tr.querySelectorAll('td')].map((t) => t.textContent);
  return { tab: (w.querySelector('.olp-tab[aria-selected=true]') || {}).dataset?.tab, title: w.querySelector('.olp-title').textContent, left: r.left, right: r.right, top: r.top, width: r.width,
    colLeft: c.left, big: (w.querySelector('.olp-big') || {}).textContent || '', err: (w.querySelector('.olp-err') || {}).textContent || '', vals, ghosts: w.querySelectorAll('.olp-ghost').length,
    segs: w.querySelectorAll('.olp-seg').length, heads: [...w.querySelectorAll('.olp-cmp thead tr:last-child th')].map((t) => t.textContent),
    rows: [...w.querySelectorAll('.olp-cmp tbody tr')].map((tr) => ({ rep: tr.classList.contains('rep'), diff: tr.querySelectorAll('td.diff').length, samp: !!tr.querySelector('.olp-samp'),
      act: (tr.querySelector('td.act button') || {}).textContent || '' })), foot: [...w.querySelectorAll('.olp-foot button')].map((b) => [b.textContent, b.disabled]) }; }"""


def main():
    wait_server()
    r = requests.post(base + "/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")}, timeout=120)
    assert r.status_code == 200, r.text
    doc = r.json()["docId"]
    run_stage(doc, 1)
    run_stage(doc, 2)
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1600, "height": 950}, device_scale_factor=1)
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/#w={doc}")
        page.wait_for_selector("#doc .para[data-id=p970]", timeout=60000)
        page.wait_for_function("() => heads.outline && document.querySelectorAll('.tpl-mark').length > 20", timeout=30000)

        # ---- 서식 비교 — T3 L2(서식 3가지)
        page.evaluate("() => tplRelOpen(3, { tpl: '3', level: 2, para: 'p5209' })")
        page.wait_for_function("() => /서식 3가지/.test((document.querySelector('#headsDlgBody .olm[data-tpl=\"3\"][data-level=\"2\"] .olm-sum') || {}).textContent || '')", timeout=30000)
        page.locator('#headsDlgBody .olm[data-tpl="3"][data-level="2"] > button', has_text="비교").click()
        page.wait_for_selector("#olpWin:not([hidden]) .olp-cmp tbody tr", timeout=20000)
        w = page.evaluate(WIN)
        check("「비교」 → 떠 있는 창 「서식 비교」 탭 · 제목 T3 L2 · 「템플릿 관계」 열과 안 겹침", w and w["tab"] == "cmp" and w["title"].startswith("T3 L2") and w["right"] <= w["colLeft"] + 1, w)
        check("갈래 3줄 · 대표가 먼저 · 다른 항목 열만(앞 공백 · 레터 뒤 공백) · 다른 값 칸 강조 · 견본 글",
              w and len(w["rows"]) == 3 and w["rows"][0]["rep"] and not any(x["rep"] for x in w["rows"][1:]) and w["heads"][1:3] == ["앞 공백", "레터 뒤 공백"]
              and all(x["diff"] >= 1 for x in w["rows"][1:]) and w["rows"][0]["diff"] == 0 and all(x["samp"] for x in w["rows"]), w)
        check("갈래마다 「맞추기」(대표 빼고) · 아래 「대표에 맞추기(2줄)」", w and [x["act"] for x in w["rows"]] == ["", "맞추기", "맞추기"] and ["대표에 맞추기(2줄)", False] in w["foot"], w and (w["rows"], w["foot"]))
        n0 = len(w["heads"])
        page.locator("#olpWin .olp-chk input").check()
        page.wait_for_timeout(150)
        n1 = len(page.evaluate(WIN)["heads"])
        check("「같은 값도 보기」 → 열이 늘어남(글꼴·크기 …)", n1 > n0 + 5, [n0, n1])
        page.locator("#olpWin .olp-chk input").uncheck()
        page.screenshot(path=str(OUT / "01_compare.png"))
        page.locator("#olpWin .olp-cmp tbody tr").nth(1).locator(".olp-samp").click()
        page.wait_for_timeout(500)
        check("견본 글을 누르면 문서로 가고 창은 열린 채", page.evaluate("() => !document.getElementById('olpWin').hidden"))
        page.locator("#olpWin .olp-foot button", has_text="대표에 맞추기").click()
        page.wait_for_function("() => /서식 1가지/.test((document.querySelector('#olpWin .olp-big') || {}).textContent || '')", timeout=20000)
        check("창의 「대표에 맞추기」 → 창도 「서식 1가지 — 모두 같음」 으로", True)
        page.click("#undoBtn")
        page.wait_for_function("() => /서식 3가지/.test((document.querySelector('#olpWin .olp-big') || {}).textContent || '')", timeout=20000)
        check("실행 취소 → 창이 다시 서식 3가지", True)

        # ---- 자리 미리보기 — 가지 템플릿 L2 「o」(p972)
        T = page.evaluate("() => heads.outline.lines.p972.tpl")
        page.evaluate("(t) => tplRelOpen(olmKey(t), { tpl: t, level: 2, para: 'p972' })", T)
        row = f'#headsDlgBody .olf[data-tpl="{T}"][data-level="2"]'
        page.wait_for_selector(row, timeout=20000)
        page.locator(f"{row} .olf-btn").click()
        page.wait_for_selector("#olpWin:not([hidden]) .olp-fig", timeout=20000)
        w = page.evaluate(WIN)
        check("「자리 수정」 → 창이 「자리 미리보기」 · 대표 줄 그림(지금·바뀐 뒤 줄 6조각) · 값 표(지금 레터 4.2)",
              w and w["tab"] == "pos" and w["segs"] == 6 and w["vals"].get("레터 위치", [None])[0] == "4.2" and w["right"] <= w["colLeft"] + 1, w)
        page.fill(f"{row} .olf-letter", "10")
        page.wait_for_function("() => [...document.querySelectorAll('#olpWin .olp-vals tbody tr')].some((tr) => tr.querySelector('th').textContent === '레터 위치' && tr.querySelectorAll('td')[1].textContent === '10.0')", timeout=20000)
        w = page.evaluate(WIN)
        check("레터 10 을 치면 바로 바뀐 뒤 레터 10.0(+5.8) · 지금 자리 점선 · 「N줄이 바뀝니다」",
              w["vals"]["레터 위치"] == ["4.2", "10.0", "+5.8"] and w["ghosts"] >= 2 and "줄이 바뀝니다" in w["big"], w)
        # 창 안의 자리 수정 칸 — 열의 고치기 줄의 거울(레터 위치 · 글 시작 · 둘째 줄 규칙·mm)
        ED = """() => { const w = document.getElementById('olpWin'), q = (c) => w.querySelector(c); return { shown: !q('.olp-edit').hidden, letter: q('.olp-e-letter').value, text: q('.olp-e-text').value,
          mode: q('.olp-e-mode').value, l2: q('.olp-e-l2').value, l2off: q('.olp-e-l2').disabled, note: q('.olp-e-note').textContent }; }"""
        AFTER = "([name, v]) => [...document.querySelectorAll('#olpWin .olp-vals tbody tr')].some((tr) => tr.querySelector('th').textContent === name && tr.querySelectorAll('td')[1].textContent === v)"
        mode0 = page.input_value(f"{row} .olf-mode")
        e = page.evaluate(ED)
        check("창에도 자리 수정 칸 — 열의 값 그대로(레터 10 · 글 시작 = 값 표의 「글 시작 — 바뀐 뒤」 · 둘째 줄 칸은 「직접」 일 때만 켜짐)",
              e["shown"] and e["letter"] == "10" and e["text"] == w["vals"]["글 시작"][1] and e["mode"] == mode0 and e["l2off"] and "함께 움직" in e["note"], [e, w["vals"], mode0])
        x8 = f"{float(w['vals']['글 시작'][1]) - 2:.1f}"  # 글 시작을 2mm 왼쪽으로 — 레터 위치는 10 → 8
        page.fill("#olpWin .olp-e-text", x8)
        page.wait_for_function(AFTER, arg=["레터 위치", "8.0"], timeout=20000)
        e, w = page.evaluate(ED), page.evaluate(WIN)
        check("창의 「글 시작」 을 고치면 레터 위치가 같이 움직임(열·창의 레터 칸 8.0 · 바뀐 뒤 레터 8.0 · 바뀐 뒤 글 시작 = 적은 값) — 치던 칸은 그대로",
              page.input_value(f"{row} .olf-letter") == "8.0" and e["letter"] == "8.0" and e["text"] == x8 and w["vals"]["글 시작"][1] == x8
              and page.evaluate("() => document.activeElement === document.querySelector('#olpWin .olp-e-text')"), [e, w["vals"], x8])
        page.select_option("#olpWin .olp-e-mode", "mm")
        page.fill("#olpWin .olp-e-l2", "11")
        page.wait_for_function(AFTER, arg=["둘째 줄", "11.0"], timeout=20000)
        check("창의 둘째 줄 규칙 「직접」 11 → 열의 규칙·칸도 같이(직접 · 11) · 바뀐 뒤 둘째 줄 11.0",
              page.input_value(f"{row} .olf-mode") == "mm" and page.input_value(f"{row} .olf-l2") == "11" and not page.evaluate(ED)["l2off"], page.evaluate(ED))
        page.select_option("#olpWin .olp-e-mode", "text")
        page.wait_for_function("() => document.querySelector('#olpWin .olp-e-l2').disabled && document.querySelector('#olpWin .olp-e-l2').value === document.querySelector('#olpWin .olp-e-text').value", timeout=20000)
        check("규칙 「글 시작에 맞춤」 → 꺼진 둘째 줄 칸에 규칙이 정한 값(= 글 시작)이 보임 — 열의 꺼진 칸도 같은 값",
              page.input_value(f"{row} .olf-l2") == page.evaluate(ED)["l2"] == x8, [page.input_value(f"{row} .olf-l2"), page.evaluate(ED), x8])
        page.fill("#olpWin .olp-e-text", "1")
        page.wait_for_function("() => /글 시작이 레터와 글 사이/.test((document.querySelector('#olpWin .olp-err') || {}).textContent || '')", timeout=20000)
        check("레터·빈칸 폭보다 작은 글 시작 → 창에 까닭(서버에 묻기 전에) · 칸은 그대로 보임", page.evaluate(ED)["shown"], page.evaluate(ED))
        page.select_option("#olpWin .olp-e-mode", mode0)
        page.fill("#olpWin .olp-e-letter", "10")
        page.wait_for_function(AFTER, arg=["레터 위치", "10.0"], timeout=20000)
        check("창의 「레터 위치」 10 → 열의 레터 칸도 10 · 글 시작 칸이 따라옴(값 표의 바뀐 뒤 글 시작)", page.input_value(f"{row} .olf-letter") == "10"
              and page.evaluate(ED)["text"] == page.evaluate(WIN)["vals"]["글 시작"][1], [page.evaluate(ED), page.evaluate(WIN)["vals"]])
        page.select_option(f"{row} .olf-mode", "mm")
        page.fill(f"{row} .olf-l2", "12")
        page.wait_for_function("() => [...document.querySelectorAll('#olpWin .olp-vals tbody tr')].some((tr) => tr.querySelector('th').textContent === '둘째 줄' && tr.querySelectorAll('td')[1].textContent === '12.0')", timeout=20000)
        w = page.evaluate(WIN)
        check("둘째 줄 「직접」 12 → 바뀐 뒤 둘째 줄 12.0 · 첫 줄 「내어쓰기 6.2」", w["vals"]["둘째 줄"][1] == "12.0" and w["vals"]["첫 줄"][1] == "내어쓰기 6.2", w["vals"])
        page.screenshot(path=str(OUT / "02_position.png"))
        page.locator("#olpWin .olp-foot button", has_text="적용").click()
        page.wait_for_function("() => (document.querySelector('#olpWin .olp-big') || {}).textContent === '바뀌는 줄 없음'", timeout=30000)
        fm = page.evaluate("() => (state.byId.get('p972') || {}).format || {}")
        check("창의 「적용」 → 문서가 바뀜(왼쪽 여백 5.77 · 내어쓰기 6.23) · 미리보기는 「바뀌는 줄 없음」",
              abs((fm.get("indentLeftMm") or 0) - 5.77) < 0.05 and abs((fm.get("firstLineMm") or 0) + 6.23) < 0.05, fm)
        page.click("#undoBtn")
        page.wait_for_function("() => Math.abs(((state.byId.get('p972') || {}).format || {}).firstLineMm || 0) < 0.02", timeout=20000)
        check("실행 취소 → 처음 여백", True)
        page.locator(f"{row} .olf-btn").click() if page.locator(f"{row} .olf-edit").is_hidden() else None
        page.wait_for_selector(f"{row} .olf-edit:not([hidden])", timeout=10000)
        page.fill(f"{row} .olf-letter", "1")
        page.wait_for_function("() => /앞 공백/.test((document.querySelector('#olpWin .olp-err') || {}).textContent || '')", timeout=20000)
        check("앞 공백 폭보다 작은 레터 위치 → 창에 까닭(적용 전에)", True)

        # ---- 닫기 · 옮기기 · 좁은 창
        page.locator(f"{row} .olf-btn").click()
        page.wait_for_timeout(200)
        check("「자리 수정」 을 접으면 창이 닫힘", page.evaluate("() => document.getElementById('olpWin').hidden"))
        page.locator('#headsDlgBody .olf-btn').first.click()
        page.wait_for_selector("#olpWin:not([hidden])", timeout=10000)
        box = page.locator("#olpWin .olp-title").bounding_box()
        x0 = page.evaluate("() => document.getElementById('olpWin').getBoundingClientRect().left")
        page.mouse.move(box["x"] + 10, box["y"] + 5)
        page.mouse.down()
        page.mouse.move(box["x"] + 110, box["y"] + 45, steps=6)
        page.mouse.up()
        x1 = page.evaluate("() => document.getElementById('olpWin').getBoundingClientRect().left")
        check("머리를 끌면 창이 옮겨짐", abs((x1 - x0) - 100) < 3, [x0, x1])
        page.locator("#olpWin .olp-tab[data-tab=cmp]").click()
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        check("Esc 로 닫힘", page.evaluate("() => document.getElementById('olpWin').hidden"))
        page.set_viewport_size({"width": 480, "height": 900})
        page.evaluate("() => { OLP.at = null; }")
        page.evaluate("() => tplRelOpen(3, { tpl: '3', level: 2, para: 'p5209' })")
        page.wait_for_selector('#headsDlgBody .olm[data-tpl="3"][data-level="2"] > button.olm-cmp', timeout=20000)
        page.locator('#headsDlgBody .olm[data-tpl="3"][data-level="2"] > button.olm-cmp').click()
        page.wait_for_selector("#olpWin:not([hidden]) .olp-cmp", timeout=20000)
        g = page.evaluate("() => { const r = document.getElementById('olpWin').getBoundingClientRect(); return [r.left, r.right, innerWidth, document.documentElement.scrollWidth]; }")
        check("좁은 창(480px) — 창이 화면 안 · 가로 넘침 없음", g[0] >= 0 and g[1] <= g[2] + 1 and g[3] <= g[2] + 1, g)
        page.screenshot(path=str(OUT / "03_narrow.png"))
        b.close()
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
