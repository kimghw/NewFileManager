"""줄 오른쪽의 서식 아이콘(spec_hwpx_웹편집 ② §8-14 — app/static/outline_spot.js) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음).

연구개발계획서 양식(1·2단계를 끝점으로): T1 「N. › N-N. › (N) › o › -」 L4 「o」.
- 「서식」 묶음이 꺼져 있으면 헤딩 줄을 눌러도 띠가 없다.
- 「서식」 묶음을 켜고 헤딩 줄을 누름 → 그 쪽 **오른쪽 여백**(본문 밖 · 그 줄 높이)에 띠 — 단추 둘 「헤딩 고치기」 · 「템플릿 나누기 · 합치기」(이름은 풍선 도움말 · aria-label). 「지침 적기」 와 겹치지 않는다.
- 「헤딩 고치기」 단추 → 그 줄의 창(#olTune) · Esc 로 닫힘 · 띠는 그 줄에 그대로.
- 「템플릿 나누기 · 합치기」 단추 → 라벨의 오른쪽 단추 메뉴와 같은 메뉴(「여기서만 새 템플릿으로 나누기 → T1L4a」 …) → 고르면 그 줄의 라벨이 「T1L4a L4」 · 문서 바이트 그대로.
- 본문 줄(개요 줄 아님)을 누름 → 단추 하나 「레터 넣기」 → 그 단추 곁에 메뉴(#plMenu · 창 안) · 다시 누르면 닫힘.
- 좁은 문서 창(서식 관리자 열이 열려 여백이 띠보다 좁음)에서도 띠가 본문 글을 가리지 않는다.
- 다른 묶음(페이지 보기)으로 바꾸면 띠가 없다 · 실행 취소를 끝까지 → 내려받은 파일 = 올린 바이트 · 콘솔 오류 없음.

    python -X utf8 tools/smoke_outline_spot_ui.py <출력 폴더> [--port 18499]
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
ap.add_argument("--port", type=int, default=18499)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "PYTHONUTF8": "1"}
for k in ("NFM_TASKS", "NFM_REQS", "NFM_AGENT_NOTES", "NFM_TOOL_NAMES"):  # 혼자 돌릴 때도 사용자의 설정 파일을 읽거나 고치지 않게(run_ui_gates 는 스스로 건다)
    env.setdefault(k, str(tmp / f"{k.lower()}.json"))
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:900] if detail != "" and not ok else ""), flush=True)
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


# 띠 — 어느 줄의 것 · 단추 · 자리(그 줄 · 본문 오른끝 · 「지침」 단추와 견줌)
BAR = """() => { const bar = document.querySelector('#doc .sheet > .os-bar'); if (!bar) return null;
  const p = paraEl(bar.dataset.para), r = bar.getBoundingClientRect(), pr = p.getBoundingClientRect(), sr = bar.parentElement.getBoundingClientRect();
  const pg = [...bar.parentElement.querySelectorAll(':scope > .pg-btn')].map((b) => b.getBoundingClientRect()).filter((b) => b.bottom > r.top - 1 && b.top < r.bottom + 1 && b.right > r.left && b.left < r.right);
  return { n: document.querySelectorAll('#doc .os-bar').length, para: bar.dataset.para, sameSheet: p.closest('.sheet') === bar.parentElement,
    btns: [...bar.querySelectorAll('button')].map((b) => ({ kind: b.dataset.os, label: b.getAttribute('aria-label'), title: b.title, text: b.textContent.trim(), svg: !!b.querySelector('svg'), w: Math.round(b.getBoundingClientRect().width) })),
    dy: Math.round(r.top - pr.top), outside: r.left >= pr.right - 1, inPaper: r.right <= sr.right + 1, mgr: parseFloat(bar.style.getPropertyValue('--mgr')), h: Math.round(r.height), overlapPg: pg.length,
    inPara: !!bar.closest('.para'), caretIn: (() => { const s = getSelection(); return !!(s.rangeCount && p.contains(s.anchorNode)); })() }; }"""
MARK = """(id) => { const b = [...document.querySelectorAll('#doc .tpl-mark .tm-t')].find((x) => (x.dataset.paras || '').split(',').includes(id)); return b ? b.textContent : null; }"""
MENU = """() => { const m = document.querySelector('.ctx-menu'); if (!m || m.hidden) return null; return [...m.querySelectorAll('button')].map((b) => (b.firstChild ? b.firstChild.textContent : '')); }"""


def idle(page):
    page.wait_for_function("() => !state.busy", timeout=20000)
    page.wait_for_timeout(400)


def press(page, pid):
    """그 문단의 글 위를 마우스로 누른다(커서를 그 줄에)."""
    page.keyboard.press("Escape")
    box = page.evaluate("""(id) => { const p = paraEl(id); p.scrollIntoView({ block: 'center' }); const r = p.getBoundingClientRect(); return { x: r.left + Math.min(r.width - 6, 120), y: r.top + Math.min(r.height / 2, 10) }; }""", pid)
    page.mouse.click(box["x"], box["y"])
    page.wait_for_timeout(350)


def bar_click(page, kind):
    page.click(f"#doc .os-bar button[data-os='{kind}']")


def main():
    wait_server()
    data = PLAN.read_bytes()
    r = requests.post(base + "/api/docs", files={"file": (PLAN.name, data, "application/octet-stream")}, timeout=120)
    assert r.status_code == 200, r.text
    doc = r.json()["docId"]
    run_stage(doc, 1)
    run_stage(doc, 2)
    ov = requests.get(f"{base}/api/docs/{doc}/outline", timeout=60).json()
    l4 = [p for p, x in ov["lines"].items() if str(x["tpl"]) == "1" and x["level"] == 4]
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1600, "height": 950}, device_scale_factor=1)
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/#w={doc}")
        page.wait_for_selector("#doc .para", timeout=60000)
        page.wait_for_function("() => !!heads.outline && Object.keys(heads.outline.lines).length > 100", timeout=30000)
        page.wait_for_timeout(600)
        page.evaluate("() => setToolSet('page')")
        # 본문의 L4 줄(표 밖 · 헤딩 고치기를 할 수 있는 줄) · 본문 줄(개요 줄 아님 · 표 밖 · 글 있음)
        head = page.evaluate("(ids) => ids.find((id) => { const p = paraEl(id); return p && !p.closest('td') && oltLineOk(p); })", l4)
        body = page.evaluate("""() => { const p = [...document.querySelectorAll('#doc .para[data-id]')].find((q) => !q.closest('td') && !outlineLine(q) && readText(q).trim().length > 12 && q.getBoundingClientRect().height > 0);
          return p ? p.dataset.id : null; }""")
        assert head and body, (head, body)

        press(page, head)
        check("「서식」 묶음이 꺼져 있으면 띠가 없다", page.evaluate(BAR) is None)

        page.click('#toolModes [data-tool="style"]')
        page.wait_for_timeout(500)
        press(page, head)
        narrow = page.evaluate(BAR)
        check("좁은 문서 창(서식 관리자 열이 열림 · 여백 < 띠 폭) — 띠가 본문 글을 가리지 않는다(종이 밖으로 조금 나가도)", narrow and narrow["outside"] and narrow["overlapPg"] == 0, narrow)
        page.screenshot(path=str(OUT / "bar_narrow.png"))
        page.evaluate("() => headsColClose()")   # 서식 관리자 열을 닫아 문서를 넓게(묶음은 켜진 채)
        page.wait_for_timeout(900)
        press(page, head)
        v = page.evaluate(BAR)
        page.screenshot(path=str(OUT / "bar_heading.png"))
        clip = page.evaluate("() => { const r = document.querySelector('#doc .os-bar').getBoundingClientRect(); return { x: Math.max(0, r.left - 420), y: Math.max(0, r.top - 60), width: 560, height: 150 }; }")
        page.screenshot(path=str(OUT / "bar_heading_clip.png"), clip=clip)
        check("「서식」 묶음 + 헤딩 줄 누름 → 띠 하나 · 그 줄의 것 · 문단 요소 밖(.sheet 의 자식) · 커서는 그 줄에", v and v["n"] == 1 and v["para"] == head and v["sameSheet"] and not v["inPara"] and v["caretIn"], v)
        check("자리 — 오른쪽 여백(본문 밖 · 종이 안) · 그 줄 높이 · 「지침」 단추와 겹치지 않음", v and v["outside"] and (v["inPaper"] or v["mgr"] < 60) and v["mgr"] >= 60 and -2 <= v["dy"] <= 4 and v["h"] == 22 and v["overlapPg"] == 0, v)
        kinds = [x["kind"] for x in v["btns"]] if v else []
        check("단추 둘 — 「헤딩 고치기」 · 「템플릿 나누기 · 합치기」(아이콘 · 글 없음 · 이름은 풍선 도움말 · aria-label)",
              kinds == ["tune", "cut"] and all(x["svg"] and x["text"] == "" and x["title"].startswith(x["label"]) for x in v["btns"])
              and v["btns"][0]["label"].startswith("헤딩 고치기 — T1 L4") and v["btns"][1]["label"] == "템플릿 나누기 · 합치기 — T1 L4", v and v["btns"])

        bar_click(page, "tune")
        page.wait_for_selector("#olTune", timeout=15000)
        t = page.evaluate("() => ({ label: document.getElementById('olTune').getAttribute('aria-label'), bar: !!document.querySelector('#doc .os-bar') })")
        check("「헤딩 고치기」 단추 → 그 줄의 창(#olTune) · 띠는 그대로", t["label"].startswith("헤딩 고치기 — T1 L4") and t["bar"], t)
        page.screenshot(path=str(OUT / "tune.png"))
        page.keyboard.press("Escape")
        page.wait_for_function("() => !document.getElementById('olTune')", timeout=5000)

        press(page, head)
        bar_click(page, "cut")
        page.wait_for_function("() => { const m = document.querySelector('.ctx-menu'); return !!m && !m.hidden; }", timeout=10000)
        items = page.evaluate(MENU)
        page.screenshot(path=str(OUT / "cut_menu.png"))
        check("「템플릿 나누기 · 합치기」 단추 → 라벨 메뉴와 같은 메뉴", items and items[0] == "여기서만 새 템플릿으로 나누기 → T1L4a" and items[1] == "T1 L4 모두 새 템플릿으로 나누기 → T1L4a" and items[-1] == "템플릿 관계에서 보기", items)
        before = page.evaluate("() => state.undo")
        page.evaluate("() => [...document.querySelectorAll('.ctx-menu button')].find((x) => x.textContent.startsWith('여기서만 새 템플릿으로')).click()")
        page.wait_for_function("(n) => state.undo !== n && !state.busy", arg=before, timeout=20000)
        idle(page)
        page.wait_for_timeout(900)
        v = page.evaluate(BAR)
        check("메뉴에서 「여기서만」 → 그 줄의 라벨 「T1L4a L4」 · 띠의 이름도 T1L4a · 문서 바이트 그대로",
              (page.evaluate(MARK, head) or "").startswith("T1L4a L4") and v and v["para"] == head and v["btns"][0]["label"].startswith("헤딩 고치기 — T1L4a L4")
              and requests.get(f"{base}/api/docs/{doc}/download", timeout=60).content == data, [page.evaluate(MARK, head), v])

        press(page, body)
        v = page.evaluate(BAR)
        check("본문 줄(개요 줄 아님) → 단추 하나 「레터 넣기」 · 그 줄 높이 · 오른쪽 여백", v and v["para"] == body and [x["kind"] for x in v["btns"]] == ["letter"]
              and v["btns"][0]["label"] == "레터 넣기 — 이 문단을 헤딩으로" and v["outside"] and -2 <= v["dy"] <= 4, v)
        bar_click(page, "letter")
        page.wait_for_selector("#plMenu", timeout=15000)
        page.wait_for_timeout(150)
        m = page.evaluate("""() => { const b = document.getElementById('plMenu'), r = b.getBoundingClientRect(), a = document.querySelector('#doc .os-bar button').getBoundingClientRect();
          return { inView: r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight, near: Math.abs(r.left - a.left) < 400 && (r.top >= a.bottom - 1 || r.bottom <= a.top + 1),
            levels: [...b.querySelectorAll('.pl-row .pl-chip')].map((c) => c.dataset.level) }; }""")
        page.screenshot(path=str(OUT / "letter_menu.png"))
        check("「레터 넣기」 단추 → 그 단추 곁(아래 또는 위)에 메뉴 · 창 안 · 이 문서의 개요 레벨이 있다", m["inView"] and m["near"] and "1|4" in m["levels"], m)
        bar_click(page, "letter")
        page.wait_for_timeout(200)
        check("단추를 다시 누르면 메뉴가 닫힌다", page.evaluate("() => !document.getElementById('plMenu')"))
        page.click('#toolModes [data-tool="page"]')
        page.wait_for_timeout(300)
        check("다른 묶음(페이지 보기)으로 바꾸면 띠가 없다", page.evaluate(BAR) is None)
        page.evaluate("() => setToolSet('style')")
        page.wait_for_timeout(300)
        check("다시 「서식」 묶음 → 마지막 줄에 띠", (page.evaluate(BAR) or {}).get("para") == body)

        for _ in range(10):
            if not page.evaluate("() => state.undo"):
                break
            page.click("#undoBtn")
            idle(page)
        check("실행 취소를 끝까지 → 내려받은 파일 = 올린 바이트", page.evaluate("() => state.undo") == 0 and requests.get(f"{base}/api/docs/{doc}/download", timeout=60).content == data)
        check("콘솔 오류 없음", not errors, errors[:5])
        page.close()


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
