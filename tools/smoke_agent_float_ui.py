"""에이전트 창(spec_일반편집 ② §12 「에이전트 창」 — app/static/agent_float.js · agent_float.css) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.
끝점은 모두 진짜(흉내 없음). 2026-11-18 사용자 「대시보드 옆 에이전트는 워크플로우 아이콘 옆 에이전트아이콘으로 하고 지금 그 아이콘 내부 내용은 거기서 설정창 아이콘을 누르면 그게 볼 수 있도록 해줘,
에이전트 아이콘을 누르면 팝업으로 지금과 같은 대시보드 옆 에이전트 사이드패널 크기를 띄어줘, .. 그리고 아이콘 넣어서 지금 처럼 대시보드 옆으로 들어 갈 수 있도록 해줘」.

- 시작 화면: 상단 바 에이전트 아이콘(워크플로우 다음) → 안내 글 창(톱니 = 에이전트 설정) · 다시 누르면 닫힘.
- hwpx 문서(기본 = 떠 있는 창): 패널 탭 줄에 「에이전트」 없음 → 아이콘 → 창(에이전트 보기가 창 안 · 패널 바로 왼쪽 · 패널과 같은 폭 · 편집 도구 줄 아래 · 패널 아래 끝까지) · 아이콘 눌림 ·
  패널 탭을 바꿔도 창은 그대로 · showTab('Agent')(대시보드 · 작업 진행 에이전트가 부르는 길)도 창을 연다(패널은 그대로) · 머리를 끌어 옮김(기억) · 두 번 누르면 처음 자리(기억 지움).
- 「패널에 넣기」: 창이 닫히고 「대시보드」 바로 옆 탭 「에이전트」 가 고른 꼴 · 보기는 패널 안 · 상태 줄 끝에 톱니 · 「창으로 띄우기」 · 초점은 탭 · 기억(새로 고쳐도 패널 탭) ·
  아이콘 = 그 탭 ↔ 그 전 도구. 「창으로 띄우기」: 다시 창 · 탭 없음 · 패널은 그 전 도구 · 초점은 「패널에 넣기」. ✕: 닫힘 · 보기는 감춤 · 초점은 아이콘.
- 일반 문서(TASK 「문서 일반 편집」)를 열면 창이 저절로 열린다(패널은 검증) · docx 문서는 안내 글(「DOCX」) · 시작 화면으로 가면 창이 닫힌다.
- 좁은 창(800px — 패널이 문서 아래로): 창 폭은 520px 까지 · 화면 안. 콘솔 오류 없음.

    python -X utf8 tools/smoke_agent_float_ui.py <출력 폴더> [--port 18460]
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
ap.add_argument("--port", type=int, default=18460)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"), "PYTHONUTF8": "1"}
for k in ("NFM_LLM_MODEL_FORCE", "NFM_LLM_MODEL", "NFM_TPL_AGENT_MODEL"):
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
            if requests.get(base + "/api/status", timeout=2).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.4)
    raise SystemExit("서버가 안 뜸")


def upload(name):
    p = ROOT / "samples" / name
    return requests.post(f"{base}/api/docs?new=1", files={"file": (name, p.read_bytes())}, timeout=180).json()["docId"]


def open_work(page, wid):
    page.evaluate("(id) => { location.hash = '#w=' + id; }", wid)
    page.reload()
    page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet') != null", arg=wid, timeout=120000)
    page.wait_for_timeout(300)


# 창 · 탭 · 보기의 지금 모양
SNAP = """() => { const f = document.getElementById('agentFloat'), pane = document.getElementById('paneAgent'), panel = document.getElementById('panel'), t = document.getElementById('tabAgent');
  const R = (e) => { const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height), Math.round(r.right), Math.round(r.bottom)]; };
  return { open: !!f && !f.hidden, inFloat: !!f && f.contains(pane), inPanel: panel.contains(pane), paneHidden: pane.hidden, tool: panel.dataset.tool || '', tab: !t.hidden, tabSel: t.getAttribute('aria-selected'),
    tabAfterDash: t.previousElementSibling && t.previousElementSibling.id, pressed: document.getElementById('agentBtn').getAttribute('aria-pressed'), mode: localStorage.getItem('nfm.agentDock'),
    saved: localStorage.getItem('nfm.agentFloat'), focus: document.activeElement ? document.activeElement.id || document.activeElement.className : '',
    rect: f && !f.hidden ? R(f) : null, panel: panel.hidden ? null : R(panel), scroller: R(document.getElementById('scroller')),
    paneTools: (() => { const x = pane.querySelector('.agf-pane-tools'); return x ? getComputedStyle(x).display : null; })(),
    status: !!pane.querySelector('.ag-status'), note: f ? f.querySelector('.agf-note').hidden ? '' : f.querySelector('.agf-note').textContent : '' }; }"""


def main():
    wait_server()
    a, g, x = upload("연구개발계획서_양식.hwpx"), upload("기술수요조사서.hwpx"), upload("기술수요조사서.docx")
    put = requests.put(f"{base}/api/works/{g}/task", json={"kind": "general", "job": "doc_edit", "file": "", "project": ""}, timeout=10)
    check("일반 문서 작업(문서 일반 편집) 준비", put.ok, put.text[:200])
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1600, "height": 950}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())

        # ---- 시작 화면 — 안내 글 창
        page.goto(base)
        page.evaluate("() => { try { localStorage.clear(); } catch {} }")
        page.reload()
        page.wait_for_selector("#agentBtn")
        h = page.evaluate("() => { const a = document.getElementById('agentBtn'); return { before: a.previousElementSibling.id, pressed: a.getAttribute('aria-pressed'), float: !!document.getElementById('agentFloat') && !document.getElementById('agentFloat').hidden }; }")
        check("시작 화면 — 워크플로우 다음에 에이전트 아이콘 · 창은 닫혀 있음", h["before"] == "workflowLink" and h["pressed"] == "false" and not h["float"], h)
        page.click("#agentBtn")
        page.wait_for_selector("#agentFloat:not([hidden])")
        s = page.evaluate("() => ({ note: document.querySelector('#agentFloat .agf-note').textContent, gear: document.getElementById('agentSettings').getAttribute('href'), pressed: document.getElementById('agentBtn').getAttribute('aria-pressed'), pane: document.getElementById('agentFloat').contains(document.getElementById('paneAgent')) })")
        check("아이콘 → 안내 글 창(「문서를 열면 …」 · 톱니 = /agents · 아이콘 눌림 · 에이전트 보기는 패널에 그대로)", "문서를 열면" in s["note"] and s["gear"] == "/agents" and s["pressed"] == "true" and not s["pane"], s)
        page.screenshot(path=str(OUT / "01_home.png"))
        page.click("#agentBtn")
        check("다시 누르면 닫힘", page.evaluate("() => document.getElementById('agentFloat').hidden"))

        # ---- hwpx 문서 — 떠 있는 창(기본)
        open_work(page, a)
        s = page.evaluate(SNAP)
        check("hwpx 문서 — 패널 탭 줄에 「에이전트」 없음(떠 있는 창 자리) · 창은 닫힘 · 아이콘 안 눌림", not s["tab"] and not s["open"] and s["pressed"] == "false" and s["mode"] is None, s)
        tool0 = s["tool"]
        page.click("#agentBtn")
        page.wait_for_function("() => !document.getElementById('agentFloat').hidden && !!document.querySelector('#agentFloat #paneAgent .ag-status')", timeout=20000)
        s = page.evaluate(SNAP)
        r, pr, sc = s["rect"], s["panel"], s["scroller"]
        check("아이콘 → 창 — 에이전트 보기가 창 안(보임) · 패널은 그 전 도구 그대로 · 아이콘 눌림 · 상태 줄의 톱니·띄우기는 창 안에서 감춤",
              s["open"] and s["inFloat"] and not s["paneHidden"] and s["tool"] == tool0 and s["pressed"] == "true" and s["paneTools"] == "none" and s["status"], s)
        check("창의 처음 자리 — 패널 바로 왼쪽(겹치지 않음) · 패널과 같은 폭 · 편집 도구 줄·파일명 줄 아래(문서 보기 위 끝부터) · 패널 아래 끝까지",
              r[4] <= pr[0] and pr[0] - r[4] <= 12 and abs(r[2] - pr[2]) <= 2 and r[1] >= sc[1] and r[1] - sc[1] <= 12 and abs(r[5] - pr[5]) <= 12, [r, pr, sc])
        page.screenshot(path=str(OUT / "02_float.png"))
        page.click("#tabHeads")
        page.wait_for_timeout(300)
        s = page.evaluate(SNAP)
        check("패널 탭(헤딩 추출)을 바꿔도 창 · 보기는 그대로", s["open"] and not s["paneHidden"] and s["tool"] == "Heads", s)
        page.click("#agentFloatClose")
        s = page.evaluate(SNAP)
        check("✕ — 창 닫힘 · 보기는 감춤 · 아이콘 안 눌림 · 초점은 아이콘", not s["open"] and s["paneHidden"] and s["pressed"] == "false" and s["focus"] == "agentBtn", s)
        page.evaluate("() => showTab('Agent')")
        page.wait_for_timeout(200)
        s = page.evaluate(SNAP)
        check("showTab('Agent')(대시보드 · 작업 진행 에이전트가 부르는 길) — 창이 열리고 패널은 그대로", s["open"] and not s["paneHidden"] and s["tool"] == "Heads", s)

        # 옮기기 · 처음 자리로
        hb = page.locator("#agentFloat .agf-head").bounding_box()
        page.mouse.move(hb["x"] + 140, hb["y"] + 18)
        page.mouse.down()
        page.mouse.move(hb["x"] - 160, hb["y"] + 90, steps=6)
        page.mouse.up()
        s = page.evaluate(SNAP)
        check("머리를 끌면 옮겨지고 그 자리를 기억", s["rect"][0] < r[0] - 200 and s["rect"][1] > r[1] + 50 and s["saved"] and '"x"' in s["saved"], [s["rect"], r, s["saved"]])
        page.dblclick("#agentFloat .agf-title")
        page.wait_for_timeout(150)
        s = page.evaluate(SNAP)
        check("머리를 두 번 누르면 처음 자리(패널 옆) · 기억 지움", abs(s["rect"][0] - r[0]) <= 2 and abs(s["rect"][1] - r[1]) <= 2 and s["saved"] is None, [s["rect"], r])

        # ---- 패널에 넣기
        page.click("#agentDock")
        page.wait_for_timeout(300)
        s = page.evaluate(SNAP)
        check("「패널에 넣기」 — 창 닫힘 · 「대시보드」 바로 옆 탭 「에이전트」 가 고른 꼴 · 보기는 패널 안 · 상태 줄 끝에 톱니·띄우기 · 초점은 탭 · 기억",
              not s["open"] and s["tab"] and s["tabSel"] == "true" and s["tabAfterDash"] == "tabDash" and s["tool"] == "Agent" and s["inPanel"] and not s["paneHidden"]
              and s["paneTools"] not in (None, "none") and s["focus"] == "tabAgent" and s["mode"] == "panel" and s["pressed"] == "true", s)
        gear = page.evaluate("() => { const a = document.querySelector('#paneAgent .agf-pane-tools a'); return [a.getAttribute('href'), a.target, a.getAttribute('aria-label')]; }")
        check("패널 탭 자리의 톱니 = 에이전트 설정(/agents · 새 탭)", gear == ["/agents", "_blank", "에이전트 설정"], gear)
        page.locator("#panel").screenshot(path=str(OUT / "03_docked_panel.png"))
        page.click("#agentBtn")
        page.wait_for_timeout(200)
        s1 = page.evaluate(SNAP)
        page.click("#agentBtn")
        page.wait_for_timeout(200)
        s2 = page.evaluate(SNAP)
        check("패널 탭 자리의 아이콘 — 누르면 그 전 도구(헤딩 추출)로 · 다시 누르면 에이전트", s1["tool"] == "Heads" and s1["pressed"] == "false" and s2["tool"] == "Agent" and s2["pressed"] == "true", [s1["tool"], s2["tool"]])
        page.reload()
        page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet') != null", arg=a, timeout=120000)
        page.wait_for_timeout(300)
        s = page.evaluate(SNAP)
        check("새로 고쳐도 패널 탭 자리(기억) — 「에이전트」 탭이 있고 창은 없음", s["tab"] and not s["open"] and s["mode"] == "panel", s)
        page.click("#tabAgent")
        page.wait_for_selector("#paneAgent .agf-undock")
        page.click("#paneAgent .agf-undock")
        page.wait_for_timeout(300)
        s = page.evaluate(SNAP)
        check("「창으로 띄우기」 — 창 · 보기는 창 안 · 탭 없음 · 패널은 다른 도구 · 초점은 「패널에 넣기」 · 기억",
              s["open"] and s["inFloat"] and not s["paneHidden"] and not s["tab"] and s["tool"] not in ("Agent", "") and s["focus"] == "agentDock" and s["mode"] == "float", s)

        # ---- 좁은 창 — 패널이 문서 아래로
        page.set_viewport_size({"width": 800, "height": 900})
        page.wait_for_timeout(350)
        s = page.evaluate(SNAP)
        check("800px — 창 폭 520px 까지 · 화면 안", s["rect"] and s["rect"][2] <= 520 and s["rect"][0] >= 0 and s["rect"][4] <= 800, s["rect"])
        page.set_viewport_size({"width": 1600, "height": 950})
        page.wait_for_timeout(300)

        # ---- 일반 문서 — 열면 창이 저절로 · docx — 안내 글 · 시작 화면으로 가면 닫힘
        page.click("#agentFloatClose")
        open_work(page, g)
        page.wait_for_function("() => !document.getElementById('agentFloat').hidden && !!document.querySelector('#agentFloat #paneAgent .ag-status')", timeout=20000)
        s = page.evaluate(SNAP)
        check("일반 문서(문서 일반 편집)를 열면 에이전트 창이 저절로 열림 · 패널은 다른 도구 · 탭 없음", s["open"] and s["inFloat"] and not s["tab"] and s["tool"] not in ("Agent", ""), s)
        open_work(page, x)
        page.wait_for_timeout(300)
        s = page.evaluate(SNAP)
        if not s["open"]:
            page.click("#agentBtn")
            page.wait_for_timeout(200)
            s = page.evaluate(SNAP)
        check("docx 문서 — 창은 안내 글(「DOCX」) · 에이전트 보기는 감춤", s["open"] and "DOCX" in s["note"] and s["paneHidden"], s)
        page.evaluate("() => goHome()")
        page.wait_for_timeout(300)
        check("시작 화면으로 가면 창이 닫힘", page.evaluate("() => document.getElementById('agentFloat').hidden && !state.id"))
        b.close()
    real = [e for e in errors if "400" not in e and "503" not in e]
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
