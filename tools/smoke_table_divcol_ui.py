"""구분 기준 열 넣기(spec_테이블매니저 ② §13 — 표 메뉴 「구분 기준 열 넣기…」) 화면 확인 —
임시 서버(임시 작업 폴더 · PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_table_divcol_ui.py <그림·임시 폴더> [--port 18471]

연구개발계획서_양식.hwpx 를 API 로 올린다(작업 종류 없음 = 연구개발과제로 본다) →
① 프로젝트 구성 값이 없을 때: 표 메뉴 「구분 기준 열 넣기…」(「프로젝트 구성에 맞추기…」 바로 뒤) → 2열 「구분 기준 열 · t1021」 = 「프로젝트 구성을 먼저 정하세요」 + 「프로젝트 구성 열기」.
② 값을 넣고(`PUT …/divisions/settings` — 기관 셋 · 단계 둘) 「다시 읽기」 → 기준 칩(기관 켜짐) · 넣을 자리(기본 「「평가 항목」 다음」 · 「개발 목표치」 묶음 안은 없음) · 값 줄 9개 ·
  차년도 칩을 켜면 열 머리 칸 둘 · 「기관 — 모두 같은 값으로…」 로 「인텍」 → 첫 줄의 칩 「가나대」 를 더 누름(「인텍, 가나대」) → 「열 넣기」 →
  문서 표의 열 수 +2 · 머리 「차년도」 「기관」 · 첫 줄 「인텍, 가나대」 · 둘째 줄 「인텍」 · 실행 취소 1번으로 되돌아감.
열 폭 넘침 · 콘솔 오류."""
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
ap.add_argument("--port", type=int, default=18471)
args = ap.parse_args()
OUT = Path(args.out).resolve()
RND = ROOT / "samples" / "연구개발계획서_양식.hwpx"
TID = "t1021"   # 「연구개발성과 성능 목표」 표(13열 — 머리 3행)
VALUES = {"stages": [2, 1], "orgs": {"lead": "인텍", "joint": ["가나대", "다라연"], "nonprofit": [False, True, False]},
          "period": {"start": "2026-03-01", "end": "2028-12-31"}, "current": 1}

OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"),
       "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"), "NFM_JOBS": "off", "NFM_DIVISION_PRESETS": str(tmp / "presets.json"),
       "NFM_TASKS": str(tmp / "tasks.json"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:500] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def menu(page):
    return page.evaluate("""() => { const m = document.querySelector('.ctx-menu'); if (!m || m.hidden || m.dataset.by !== 'tmn') return null;
        return [...m.querySelectorAll('button')].map((b) => ({text: b.textContent, disabled: b.disabled})); }""")


def corner(page, tid):
    page.locator(f"#doc table.tbl[data-tbl='{tid}'] td .para").first.scroll_into_view_if_needed()
    page.wait_for_timeout(1200)
    page.locator(f"#doc table.tbl[data-tbl='{tid}'] td .para").first.click()
    page.wait_for_selector(f".tbl-corner[data-for='{tid}']")
    page.locator(".tbl-corner").click()
    page.wait_for_selector(".ctx-menu[data-by='tmn']:not([hidden])")


VIEW = """() => { const w = document.querySelector('.tdc-wrap'); if (!w) return null; const txt = (e) => (e ? e.textContent : '');
  return { title: document.getElementById('headsDlgTitle').textContent, kind: heads.dlg, notes: [...w.querySelectorAll('p.hnote')].map(txt),
    bases: [...w.querySelectorAll('.tdc-bases label')].map((l) => [l.textContent, l.querySelector('input').checked, l.querySelector('input').disabled]),
    at: (() => { const s = w.querySelector('select.tdc-at'); return s ? [...s.options].map((o) => [o.textContent, o.selected]) : null; })(),
    heads: [...w.querySelectorAll('input.tdc-head')].map((i) => i.value), rows: [...w.querySelectorAll('table.tdc-rows tbody tr')].map((tr) => ({ name: txt(tr.querySelector('.tdc-name')),
      outs: [...tr.querySelectorAll('.tdc-out')].map(txt) })), sum: txt(w.querySelector('.tdc-bar .muted')), go: (w.querySelector('.tdc-go') || {}).disabled,
    btns: [...w.querySelectorAll('button.btn')].map(txt) }; }"""
FIT = """() => { const p = document.getElementById('headsDlg'), r = p.getBoundingClientRect();
  const bad = [...p.querySelectorAll('.tdc-wrap *')].filter(e => e.getClientRects().length && (e.getBoundingClientRect().right > r.right + 1 || e.getBoundingClientRect().left < r.left - 1)).slice(0, 6).map(e => e.className || e.tagName);
  return { width: Math.round(r.width), bad, bodyOver: document.getElementById('headsDlgBody').scrollWidth - document.getElementById('headsDlgBody').clientWidth }; }"""
GRID = """(tid) => { const b = xlBlock(tid); if (!b) return null; const g = {}; for (const c of b.cells) g[`${c.row},${c.col}`] = (c.text || '').trim(); return { cols: b.nCols, g }; }"""

try:
    for _ in range(240):
        try:
            if requests.get(f"{base}/api/headings/llm", timeout=2).status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(0.5)
    r = requests.post(f"{base}/api/docs?new=1", files={"file": (RND.name, RND.read_bytes())}, timeout=120)
    r.raise_for_status()
    doc = r.json()["docId"]
    g0 = requests.get(f"{base}/api/docs/{doc}/tables/{TID}/divcol", timeout=120).json()
    check("서버 — 관문 안 · 프로젝트 구성 없음(ready false)", g0.get("gate") == "rnd" and g0.get("ready") is False, g0)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1700, "height": 1000})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("dialog", lambda d: (errors.append(f"dialog: {d.message}"), d.accept()))
        page.goto(f"{base}/#w={doc}")
        page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=240000)
        page.wait_for_timeout(1500)

        # ---- 1. 표 메뉴의 새 항목 · 프로젝트 구성 없음
        corner(page, TID)
        m = menu(page)
        texts = [x["text"] for x in m]
        at = lambda s: next((i for i, t in enumerate(texts) if t.startswith(s)), -9)
        check("표 메뉴 — 「구분 기준 열 넣기…」 가 「프로젝트 구성에 맞추기…」 바로 뒤 · 켜짐", at("구분 기준 열 넣기…") == at("프로젝트 구성에 맞추기…") + 1 >= 1
              and not m[at("구분 기준 열 넣기…")]["disabled"], texts)
        page.screenshot(path=str(OUT / "1_menu.png"))
        page.locator(".ctx-menu[data-by='tmn'] button:has-text('구분 기준 열 넣기')").first.click()
        page.wait_for_function("() => { const w = document.querySelector('.tdc-wrap'); return w && /프로젝트 구성을 먼저/.test(w.textContent); }", timeout=60000)
        v = page.evaluate(VIEW)
        check("2열 「구분 기준 열 · t1021」(kind tblDivCol) — 「프로젝트 구성을 먼저 정하세요」 · 「프로젝트 구성 열기」", v["title"] == f"구분 기준 열 · {TID}" and v["kind"] == "tblDivCol"
              and "프로젝트 구성 열기" in v["btns"], v)
        page.screenshot(path=str(OUT / "2_not_ready.png"))

        # ---- 2. 값을 넣고 다시 읽기
        pr = requests.put(f"{base}/api/docs/{doc}/divisions/settings", json={"values": VALUES}, timeout=60)
        check("프로젝트 구성 값 넣기(API)", pr.status_code == 200, pr.text[:300])
        page.locator(".tdc-wrap button:has-text('다시 읽기')").click()
        page.wait_for_selector(".tdc-wrap table.tdc-rows", timeout=60000)
        v = page.evaluate(VIEW)
        check("기준 칩 — 단계 · 차년도 · 기관(기관만 켜짐)", [(t.split(" ")[0], on) for t, on, _ in v["bases"]] == [("단계", False), ("차년도", False), ("기관", True)], v["bases"])
        sel = [t for t, s in v["at"] if s]
        check("넣을 자리 — 기본 「「평가 항목」 다음 (기본)」 · 「개발 목표치」 묶음 뒤는 있음", sel == ["「평가 항목」 다음 (기본)"] and any("개발 목표치" in t for t, _ in v["at"]), v["at"])
        check("값 줄 9개(1. ~ 9.) · 처음엔 빈 칸", [r["name"] for r in v["rows"]] == [f"{n}." for n in range(1, 10)] and all(r["outs"] == ["(빈 칸)"] for r in v["rows"]), v["rows"])
        page.locator(".tdc-bases label:has-text('차년도') input").click()
        page.wait_for_timeout(200)
        v = page.evaluate(VIEW)
        check("차년도를 켜면 머리 글 둘(차년도 · 기관) · 줄마다 두 칸", v["heads"] == ["차년도", "기관"] and all(len(r["outs"]) == 2 for r in v["rows"]), (v["heads"], v["rows"][:1]))
        page.locator(".tdc-all select.tdc-allsel").nth(1).select_option(label="인텍")
        page.wait_for_timeout(200)
        page.locator("table.tdc-rows tbody tr").first.locator("td").nth(2).locator("button:has-text('가나대')").click()
        page.locator("table.tdc-rows tbody tr").first.locator("td").nth(1).locator("button:has-text('1단계 1차년도')").click()
        v = page.evaluate(VIEW)
        check("첫 줄 「1단계 1차년도」 · 「인텍, 가나대」 · 둘째 줄 기관 「인텍」", v["rows"][0]["outs"] == ["1단계 1차년도", "인텍, 가나대"] and v["rows"][1]["outs"] == ["(빈 칸)", "인텍"], v["rows"][:2])
        check("넣기 줄 요약 · 단추 켜짐", "차년도 · 기관 열 2개" in v["sum"] and "값을 적을 줄 9" in v["sum"] and v["go"] is False, v["sum"])
        f = page.evaluate(FIT)
        check("2열 안에 맞음(넘침 없음)", not f["bad"] and f["bodyOver"] <= 1, f)
        page.locator("table.tdc-rows tbody tr").first.hover()
        hit = page.evaluate("() => document.querySelectorAll('#doc td.tdc-hit').length")
        check("줄에 올리면 문서의 그 줄 칸을 칠함", hit >= 10, hit)
        page.screenshot(path=str(OUT / "3_plan.png"))
        before = page.evaluate(GRID, TID)

        # ---- 3. 열 넣기
        page.locator(".tdc-go").click()
        page.wait_for_function("() => { const w = document.querySelector('.tdc-wrap .tdc-done'); return !!w; }", timeout=60000)
        page.wait_for_timeout(500)
        after = page.evaluate(GRID, TID)
        g = after["g"]
        check("문서 표 — 열 +2 · 머리 「차년도」 「기관」", after["cols"] == before["cols"] + 2 and g.get("0,1") == "차년도" and g.get("0,2") == "기관", (before["cols"], after["cols"], g.get("0,1"), g.get("0,2")))
        check("값 칸 — 첫 줄 「1단계 1차년도」 「인텍, 가나대」 · 둘째 줄 「」 「인텍」", g.get("3,1") == "1단계 1차년도" and g.get("3,2") == "인텍, 가나대" and g.get("4,1") == "" and g.get("4,2") == "인텍",
              [g.get(k) for k in ("3,1", "3,2", "4,1", "4,2")])
        page.screenshot(path=str(OUT / "4_done.png"))
        page.locator(f"#doc table.tbl[data-tbl='{TID}']").first.scroll_into_view_if_needed()
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT / "5_table.png"))

        # ---- 4. 실행 취소
        u = requests.post(f"{base}/api/docs/{doc}/undo", timeout=60)
        check("실행 취소 1번 — 열 수가 돌아감", u.status_code == 200 and requests.get(f"{base}/api/docs/{doc}/tables/{TID}/divcol", timeout=60).json()["cols"] == before["cols"], u.text[:200])
        browser.close()
    check("콘솔 오류 없음", not errors, errors[:5])
finally:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'FAIL ' + str(len(fails)) if fails else 'ALL PASS'}")
sys.exit(1 if fails else 0)
