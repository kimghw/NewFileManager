"""여기부터 새 템플릿으로 나누기(spec_hwpx_웹편집 ② §8-13 — app/static/outline_cut.js · app/outline_match.py `cut`) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음).

연구개발계획서 양식(1·2단계를 끝점으로): T1 「N. › N-N. › (N) › o › -」 L4 「o」 22줄.
- 여백의 라벨 「T1 L4」 를 오른쪽 단추로 → 공용 메뉴(큰 창 아님): 「여기서만 새 템플릿으로 나누기 → T1L4a」 · 「T1 L4 모두 새 템플릿으로 나누기 → T1L4a」 · 「템플릿 관계에서 보기」 —
  줄 수는 서버가 센 것(「22곳 · 총 37줄」) · 항목마다 풍선 도움말 · 문단 메뉴(구역 지정 …)는 같이 뜨지 않는다.
- 「여기서만」 → 알림 · 그 줄의 라벨 「T1L4a L4」 · 다른 자리의 줄은 「T1 L4」 그대로 · 문서 바이트 그대로 · 실행 취소 +1.
- 나눈 줄의 라벨 메뉴: 「T1L4a 전체를 T1 로 합치기」 가 있다 · 다른 「T1 L4」 줄의 메뉴: 「여기서만 T1L4a 에 넣기」 가 있다.
- 「T1 L4 모두」 → 남은 줄이 모두 「T1L4b L4」 · 문서에 「T1 L4」 라벨이 남지 않는다 · 「템플릿 관계」 의 그 템플릿 줄에 표지 「나눈 템플릿 — T1 L4 부터(줄 모두)」.
- 메뉴의 「합치기」 → 줄이 「T1 L4」 로 돌아온다.
- 띠 표 줄(별첨)의 메뉴: 나누기 두 항목이 꺼져 있고 까닭이 풍선 도움말에.
- 실행 취소를 끝까지 → 내려받은 파일 = 원본 바이트 · 콘솔 오류 없음.

    python -X utf8 tools/smoke_outline_cut_ui.py <출력 폴더> [--port 18497]
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
ap.add_argument("--port", type=int, default=18497)
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


MARK = """(id) => { const p = paraEl(id); if (!p) return null; p.scrollIntoView({ block: 'center' });
  const b = [...document.querySelectorAll('#doc .tpl-mark .tm-t')].find((x) => (x.dataset.paras || '').split(',').includes(id));
  return b ? { text: b.textContent, tpl: b.dataset.tpl, level: b.dataset.level, paras: b.dataset.paras } : null; }"""
MENU = """() => { const m = document.querySelector('.ctx-menu'); if (!m || m.hidden) return null;
  return [...m.querySelectorAll('button')].map((b) => ({ text: b.firstChild ? b.firstChild.textContent : '', tail: (b.querySelector('kbd') || {}).textContent || '', off: b.disabled, tip: b.title || '' })); }"""
STATE = """() => { const toast = document.getElementById('toast'); const ls = heads.outline ? Object.values(heads.outline.lines) : [];
  const n = (no, lv) => ls.filter((x) => String(x.no) === no && x.level === lv).length;
  return { undo: state.undo, toast: toast.hidden ? '' : toast.textContent, a4: n('1', 4), c4: n('1L4a', 4), b4: n('1L4b', 4), dialog: !!document.querySelector('dialog[open]') }; }"""


def idle(page):
    page.wait_for_function("() => !state.busy", timeout=20000)
    page.wait_for_timeout(400)


def menu(page, pid):
    """줄 pid 의 라벨을 오른쪽 단추로 눌러 메뉴를 연다 → 항목들."""
    page.keyboard.press("Escape")
    page.evaluate(MARK, pid)
    page.wait_for_timeout(250)
    box = page.evaluate("""(id) => { const b = [...document.querySelectorAll('#doc .tpl-mark .tm-t')].find((x) => (x.dataset.paras || '').split(',').includes(id));
      if (!b) return null; const r = b.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }""", pid)
    assert box, f"라벨이 없음: {pid}"
    page.mouse.click(box["x"], box["y"], button="right")
    page.wait_for_function("() => { const m = document.querySelector('.ctx-menu'); return !!m && !m.hidden; }", timeout=10000)
    return page.evaluate(MENU)


def pick(page, starts):
    """메뉴 항목을 누르고 그 요청이 끝날 때까지(실행 취소 수가 바뀔 때까지 — 나누기 · 합치기는 한 번에 +1) 기다린다."""
    before = page.evaluate("() => state.undo")
    page.evaluate("""(s) => { const b = [...document.querySelectorAll('.ctx-menu button')].find((x) => x.textContent.startsWith(s)); b.click(); }""", starts)
    page.wait_for_function("(n) => state.undo !== n && !state.busy", arg=before, timeout=20000)
    idle(page)


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
    band = next(p for p, x in ov["lines"].items() if ov["templates"][str(x["tpl"])].get("kind") == "band")
    plan = requests.get(f"{base}/api/docs/{doc}/outline/cut", params={"paras": l4[0]}, timeout=60).json()
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
        m0 = page.evaluate(MARK, l4[0])
        check("처음 — 그 줄의 라벨 「T1 L4」 · 라벨이 제 줄(data-paras)을 지닌다", m0 and m0["text"].startswith("T1 L4") and l4[0] in m0["paras"].split(","), m0)

        items = menu(page, l4[0])
        page.screenshot(path=str(OUT / "menu.png"))
        RANGE = "레벨 범위를 골라 나누기…"   # 헤딩 고치기 창을 나누기로 여는 항목(레터가 있는 개요 줄에만 — spec_hwpx_웹편집 ② §8-12 · 2026-11-24)
        print("    메뉴:", [i["text"] for i in items], flush=True)
        items = [i for i in items if i["text"] != RANGE]
        texts = [i["text"] for i in items]
        here, every = plan["here"], plan["all"]
        tail = lambda x: (f"{x['lines']}곳 · 총 {x['moved']}줄" if x["moved"] > x["lines"] else f"{x['moved']}줄")  # noqa: E731
        check("오른쪽 단추 → 메뉴: 여기서만 · T1 L4 모두 · 템플릿 관계에서 보기(큰 창 아님 · 문단 메뉴는 안 뜸)",
              texts == ["여기서만 새 템플릿으로 나누기 → T1L4a", "T1 L4 모두 새 템플릿으로 나누기 → T1L4a", "템플릿 관계에서 보기"] and not page.evaluate(STATE)["dialog"], texts)
        check("줄 수는 서버가 센 것 · 항목마다 풍선 도움말 · 꺼진 항목 없음",
              items[0]["tail"] == tail(here) and items[1]["tail"] == tail(every) and all(i["tip"] for i in items) and not any(i["off"] for i in items)
              and "다른 자리의 T1 L4 줄은 그대로" in items[0]["tip"] and "문서는 안 바뀝니다" in items[1]["tip"], items)

        pick(page, "여기서만 새 템플릿으로")
        st = page.evaluate(STATE)
        m1, m2 = page.evaluate(MARK, l4[0]), page.evaluate(MARK, l4[1])
        check("「여기서만」 → 알림 · 그 줄만 「T1L4a L4」 · 다른 줄은 「T1 L4」 · 실행 취소 +1 · 문서 바이트 그대로",
              "T1L4a 로 나눴습니다" in st["toast"] and m1 and m1["text"].startswith("T1L4a L4") and m2 and m2["text"].startswith("T1 L4") and st["undo"] == 1 and st["c4"] == 1
              and st["a4"] == len(l4) - 1 and requests.get(f"{base}/api/docs/{doc}/download", timeout=60).content == data, [st, m1, m2])

        items = menu(page, l4[0])
        check("나눈 줄의 메뉴 — 「T1L4a 전체를 T1 로 합치기」", any(i["text"] == "T1L4a 전체를 T1 로 합치기" and not i["off"] for i in items) and items[0]["text"].endswith("→ T1L4aL4a"), items)
        items = menu(page, l4[1])
        check("다른 「T1 L4」 줄의 메뉴 — 「여기서만 T1L4a 에 넣기」 · 새 이름은 T1L4b",
              any(i["text"] == "여기서만 T1L4a 에 넣기" and not i["off"] for i in items) and items[0]["text"].endswith("→ T1L4b"), items)

        pick(page, "T1 L4 모두 새 템플릿으로")
        st = page.evaluate(STATE)
        m2 = page.evaluate(MARK, l4[1])
        left = page.evaluate("() => [...document.querySelectorAll('#doc .tpl-mark .tm-t')].filter((x) => x.dataset.tpl === '1' && x.dataset.level === '4').length")
        check("「T1 L4 모두」 → 남은 줄이 모두 「T1L4b L4」 · 「T1 L4」 라벨이 남지 않는다",
              "T1L4b 로 나눴습니다" in st["toast"] and "모두" in st["toast"] and st["a4"] == 0 and st["b4"] == len(l4) - 1 and m2 and m2["text"].startswith("T1L4b L4") and left == 0, [st, m2, left])
        page.evaluate("() => tplRelOpen('1~4b')")
        page.wait_for_selector("#headsDlgBody li.trel-node", timeout=20000)
        page.wait_for_timeout(600)
        chip = page.evaluate("""() => { const li = [...document.querySelectorAll('#headsDlgBody li.trel-node')].find((x) => x.dataset.tpl === '1~4b'); if (!li) return null;
          const row = li.querySelector(':scope > .trel-row'); return { chips: [...row.querySelectorAll('.olm-chip')].map((c) => c.textContent), un: !!row.querySelector('.olm-unsplit') }; }""")
        check("「템플릿 관계」 — 그 템플릿 줄에 표지 「나눈 템플릿 — T1 L4 부터(줄 모두)」 + 「합치기」", chip and "나눈 템플릿 — T1 L4 부터(줄 모두)" in chip["chips"] and chip["un"], chip)
        page.screenshot(path=str(OUT / "after_all.png"))

        menu(page, l4[1])
        pick(page, "T1L4b 전체를 T1 로 합치기")
        st = page.evaluate(STATE)
        m2 = page.evaluate(MARK, l4[1])
        check("메뉴의 「합치기」 → 줄이 「T1 L4」 로 돌아온다", st["b4"] == 0 and st["a4"] == len(l4) - 1 and m2 and m2["text"].startswith("T1 L4") and "합쳤습니다" in st["toast"], [st, m2])

        items = menu(page, band)
        check("띠 표 줄(별첨)의 메뉴 — 나누기 두 항목이 꺼져 있고 까닭이 풍선 도움말에",
              items[0]["off"] and items[1]["off"] and "별첨" in items[0]["tip"] and "별첨" in items[1]["tip"] and not items[-1]["off"], items)
        page.keyboard.press("Escape")
        check("Esc → 메뉴 닫힘", page.evaluate(MENU) is None)

        for _ in range(10):
            if not page.evaluate(STATE)["undo"]:
                break
            page.click("#undoBtn")
            idle(page)
        m0 = page.evaluate(MARK, l4[0])
        check("실행 취소를 끝까지 → 라벨 「T1 L4」 · 내려받은 파일 = 올린 바이트",
              page.evaluate(STATE)["undo"] == 0 and m0 and m0["text"].startswith("T1 L4") and requests.get(f"{base}/api/docs/{doc}/download", timeout=60).content == data, m0)
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
