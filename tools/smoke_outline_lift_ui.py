"""표 제목을 템플릿의 L1 으로(spec_hwpx_웹편집 ② §8-7 — app/static/outline_lift.js · app/outline_lift.py) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음).

연구개발계획서 양식(1·2단계를 끝점으로): 가지 템플릿 T2 「□›o›-›·」 의 첫 레벨 줄 하나 바로 위에 1칸 제목 상자 「기술준비도(TRL, …」.
- 「템플릿 관계」 의 T2 줄에 「표를 L1 으로」 단추 → 누르면 그 아래 한 줄 펼침(팝업 아님): 「1칸 제목 표 1곳」 · 표 제목 줄(문서로) · 「L1 으로 넣기(1곳)」.
- 넣기 → 알림 · 화면의 템플릿 사슬 맨 앞 「▦」 · max 5 · 여백 표시: 제목 문단 「T2 L1」 · 그 아래 □ 「T2 L2」 · 트리: 표지 「L1 = 표 제목 1곳」 + 「떼기」 · 레벨 줄 L1 「표 제목」 · L2 「□」 · 실행 취소 1 · 문서는 그대로.
- 표 제목 줄에서 Enter → 표 아래 본문에 「□ 」 새 줄(T2 L2) · 제목 글 그대로 · Alt+↓ = 거절 알림 · 그 아래 □ 의 Alt+↑ = 거절 알림(표 제목 레벨).
- 「떼기」 → 사슬 「□›o›-›·」 · □ 「T2 L1」 · 표 줄 표시 없음.
- 실행 취소를 끝까지 → 내려받은 파일 = 원본 바이트 · 콘솔 오류 없음(뜻한 거절 400 빼고).

    python -X utf8 tools/smoke_outline_lift_ui.py <출력 폴더> [--port 18473]
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
ap.add_argument("--port", type=int, default=18473)
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


LINE = """(id) => { const p = paraEl(id); if (!p) return null; const ol = outlineLine(p);
  const mark = [...document.querySelectorAll('#doc .tpl-mark:not(.fmt)')].find((m) => Math.abs(m.getBoundingClientRect().top - p.getBoundingClientRect().top) < 8);
  return { text: readText(p), level: ol ? ol.level : null, role: ol ? ol.role : null, mark: mark ? mark.textContent : '', inCell: !!p.closest('td'), focused: document.activeElement === p }; }"""
STATE = """() => { const t = heads.outline ? heads.outline.templates['2'] : null; const toast = document.getElementById('toast');
  return { undo: state.undo, max: t ? t.max : null, chain: t ? t.chain : null, lift: t ? t.lift || null : null, toast: toast.hidden ? '' : toast.textContent }; }"""
ROW = """() => { const li = [...document.querySelectorAll('#headsDlgBody li.trel-node')].find((x) => x.dataset.tpl === '2'); if (!li) return null;
  const row = li.querySelector(':scope > .trel-row'), form = li.querySelector(':scope > .oll-form');
  return { btn: (row.querySelector('.oll-btn') || {}).textContent || '', chip: (row.querySelector('.oll-chip') || {}).textContent || '', un: !!row.querySelector('.oll-un'),
    open: !!form && !form.hidden, form: form ? form.textContent : '', go: form ? [...form.querySelectorAll('.oll-go')].map((b) => b.textContent) : [],
    links: form ? form.querySelectorAll('.oll-list li').length : 0, dialog: !!document.querySelector('dialog[open]'),
    levels: [...li.querySelectorAll(':scope > .trel-body > .trel-levels > li > .trel-level')].map((e) => e.textContent.replace(/\\s+/g, ' ').trim().slice(0, 14)) }; }"""


def focus(page, pid, at="end"):
    page.evaluate("([id, at]) => { const p = paraEl(id); p.scrollIntoView({ block: 'center' }); focusAt({ id, offset: at === 'end' ? readText(p).length : at }); }", [pid, at])
    page.wait_for_timeout(150)


def idle(page):
    page.wait_for_function("() => !state.busy", timeout=20000)
    page.wait_for_timeout(350)


def main():
    wait_server()
    r = requests.post(base + "/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")}, timeout=120)
    assert r.status_code == 200, r.text
    doc = r.json()["docId"]
    run_stage(doc, 1)
    run_stage(doc, 2)
    cand = requests.get(f"{base}/api/docs/{doc}/outline/lift", params={"tpl": "2"}, timeout=60).json()
    tb = cand["groups"][0]["tables"][0]
    para, under = tb["para"], tb["under"]
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1600, "height": 950}, device_scale_factor=1)
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/#w={doc}")
        page.wait_for_selector("#doc .para", timeout=60000)
        page.wait_for_function("() => !!heads.outline && !!heads.outline.lines['p975']", timeout=30000)
        page.evaluate("() => tplRelOpen(2)")
        page.wait_for_selector("#headsDlgBody li.trel-node", timeout=20000)
        page.wait_for_timeout(500)
        v0 = page.evaluate(LINE, under)
        row = page.evaluate(ROW)
        check("처음 — 제목 상자 아래 □ 는 「T2 L1」 · 제목 문단은 개요 줄 아님 · T2 줄에 「표를 L1 으로」 단추(접힘)",
              v0["level"] == 1 and "T2 L1" in v0["mark"] and page.evaluate(LINE, para)["level"] is None and row and row["btn"] == "표를 L1 으로" and not row["open"] and not row["chip"], [v0, row])

        # 펼치기 — 후보 한 묶음
        page.click("#headsDlgBody li.trel-node[data-tpl='2'] > .trel-row .oll-btn")
        page.wait_for_selector("#headsDlgBody li.trel-node[data-tpl='2'] > .oll-form .oll-go", timeout=20000)
        row = page.evaluate(ROW)
        check("누르면 그 아래 한 줄 펼침(팝업 아님) — 「1칸 제목 표 1곳」 · 표 제목 줄 · 「L1 으로 넣기(1곳)」",
              row["open"] and "1칸 제목 표 1곳" in row["form"] and "기술준비도(TRL" in row["form"] and row["go"] == ["L1 으로 넣기(1곳)"] and row["links"] == 1 and not row["dialog"], row)
        page.screenshot(path=str(OUT / "01_candidates.png"))

        # 넣기
        page.click("#headsDlgBody li.trel-node[data-tpl='2'] > .oll-form .oll-go")
        page.wait_for_function("() => heads.outline.templates['2'].lift && heads.outline.templates['2'].max === 5", timeout=20000)
        page.wait_for_selector("#headsDlgBody li.trel-node[data-tpl='2'] > .trel-row .oll-chip", timeout=20000)
        page.wait_for_timeout(600)
        st, a, u, row = page.evaluate(STATE), page.evaluate(LINE, para), page.evaluate(LINE, under), page.evaluate(ROW)
        check("넣기 → 사슬 맨 앞 「▦」 · max 5 · 실행 취소 1 · 알림", st["chain"] == ["▦", "□", "o", "-", "·"] and st["max"] == 5 and st["lift"]["tables"] == 1 and st["undo"] == 1 and "L1 로 넣었습니다" in st["toast"], st)
        check("여백 표시 — 제목 문단(칸 안) 「T2 L1」(표 줄) · 그 아래 □ 「T2 L2」", a["level"] == 1 and a["role"] == "table" and a["inCell"] and "T2 L1" in a["mark"] and u["level"] == 2 and "T2 L2" in u["mark"], [a, u])
        check("트리 — 표지 「L1 = 표 제목 1곳」 + 「떼기」 · 단추 「표 더 넣기」 · 레벨 줄 L1 「표 제목」 · L2 「□」",
              row["chip"] == "L1 = 표 제목 1곳" and row["un"] and row["btn"] == "표 더 넣기" and row["levels"][:2] and "표 제목" in row["levels"][0] and "□" in row["levels"][1] and len(row["levels"]) == 5, row)
        same = requests.get(f"{base}/api/docs/{doc}/download", timeout=60).content == PLAN.read_bytes()
        check("문서는 안 바뀜(내려받은 파일 = 원본 바이트)", same)
        page.screenshot(path=str(OUT / "02_lifted.png"))

        # 표 제목 줄의 Enter — 표 아래에 L2 새 줄
        title = a["text"]
        n0 = page.evaluate("() => document.querySelectorAll('#doc .para').length")
        focus(page, para, 2)
        page.keyboard.press("Enter")
        page.wait_for_function("(n) => !state.busy && document.querySelectorAll('#doc .para').length > n", arg=n0, timeout=20000)
        page.wait_for_timeout(400)
        new = page.evaluate("() => state.cur && state.cur.id")
        nv, a2 = page.evaluate(LINE, new), page.evaluate(LINE, para)
        check("표 제목 줄에서 Enter → 표 아래 본문에 「□ 」 새 줄(T2 L2) · 커서가 새 줄 · 제목 글 그대로", nv and nv["text"] == "□ " and nv["level"] == 2 and not nv["inCell"] and "T2 L2" in nv["mark"] and nv["focused"] and a2["text"] == title, [nv, a2["text"]])
        page.screenshot(path=str(OUT / "03_enter.png"))

        # 거절 — 표 줄의 Alt+↓ · 그 아래 □ 의 Alt+↑
        focus(page, para, 1)
        page.keyboard.press("Alt+ArrowDown")
        idle(page)
        t1 = page.evaluate(STATE)["toast"]
        focus(page, under, 2)
        page.keyboard.press("Alt+ArrowUp")
        idle(page)
        t2 = page.evaluate(STATE)["toast"]
        check("표 제목 줄의 Alt+↓ = 거절 알림(Enter 만) · 그 아래 □ 의 Alt+↑ = 거절 알림(표 제목 레벨로는 못 올림)",
              "Enter(표 아래에 새 줄)만" in t1 and "표 제목 레벨로는 올릴 수 없습니다" in t2 and page.evaluate(LINE, under)["level"] == 2 and not page.evaluate("() => !!document.getElementById('olGrow')"), [t1, t2])

        # 떼기
        page.click("#headsDlgBody li.trel-node[data-tpl='2'] > .trel-row .oll-un")
        page.wait_for_function("() => !heads.outline.templates['2'].lift && heads.outline.templates['2'].max === 4", timeout=20000)
        page.wait_for_timeout(600)
        st, a, u, row = page.evaluate(STATE), page.evaluate(LINE, para), page.evaluate(LINE, under), page.evaluate(ROW)
        check("「떼기」 → 사슬 「□›o›-›·」 · □ 「T2 L1」 · 표 줄 표시 없음 · 단추 「표를 L1 으로」", st["chain"] == ["□", "o", "-", "·"] and a["level"] is None and u["level"] == 1 and "T2 L1" in u["mark"]
              and row["btn"] == "표를 L1 으로" and not row["chip"] and "뺐습니다" in st["toast"], [st, a, u, row])

        # 실행 취소를 끝까지
        for _ in range(8):
            if not page.evaluate(STATE)["undo"]:
                break
            page.click("#undoBtn")
            idle(page)
        same = requests.get(f"{base}/api/docs/{doc}/download", timeout=60).content == PLAN.read_bytes()
        check("실행 취소를 끝까지 → 내려받은 파일 = 원본 바이트", page.evaluate(STATE)["undo"] == 0 and same)
        b.close()
    bad = [e for e in errors if "status of 400" not in e]  # 거절 둘(400)은 브라우저가 콘솔에 남긴다
    check("콘솔 오류 없음(뜻한 거절 400 빼고)", not bad and len(errors) <= 2, errors[:5])


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
