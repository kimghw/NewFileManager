"""양식의 표 등록부(spec_테이블매니저 ② §11 「표 · 띠 정체」 — 「테이블」 탭 표 목록 위 등록부 줄 · 표마다 「양식 표」 꼬리표) 화면 확인 —
임시 서버(임시 작업 폴더 · 임시 헤딩 저장소 · 임시 양식 정보 폴더 = 저장소 forms/연구개발계획서.md 의 사본, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_form_tables_ui.py <그림·임시 폴더> [--port 18197]

연구개발계획서_양식.hwpx(= 그 양식 정보의 match.sha256 에 든 등록된 빈 양식)를 올리고 표 구조(3단계 — 스크립트)를 API 로 만든 뒤 `#w=<id>` 로 열어:
① 「테이블」 탭 — 등록부 줄 「양식의 표 등록부 · 연구개발계획서 · 아직 없습니다」 + 「이 빈 양식으로 짓기」 · 꼬리표 없음.
② 「이 빈 양식으로 짓기」(확인 창 없음) → 서버에 등록부(표 = 3단계 표 수 · id 가 겹치지 않음) · 줄에 「표 n · 서브 테이블 m · 스크립트 판정」 · 「이 문서: 이은 표 n/n」 ·
   표마다 「양식 표」 꼬리표(모든 표 — 확실함 「?」 없음) · 꼬리표 풍선 도움말에 소속 · 병합 방식 · 서브 테이블.
③ 「등록부 보기」 → 표 목록 위에 펼친 등록부(항목 n — 이름 · 소속 · 병합 방식) · 「이 문서 t…」 표지 · 「등록부 접기」.
④ 패널 안에 들어감(가로 넘침 없음) · 문서를 안 바꿈(실행 취소 수 그대로) · 콘솔 오류 · 확인 창 없음."""
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
ap.add_argument("--port", type=int, default=18197)
args = ap.parse_args()
OUT = Path(args.out).resolve()
RND = ROOT / "samples" / "연구개발계획서_양식.hwpx"
FORM = "연구개발계획서"

OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
(tmp / "forms").mkdir(parents=True, exist_ok=True)
shutil.copy(ROOT / "forms" / f"{FORM}.md", tmp / "forms" / f"{FORM}.md")
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_JOBS": "off", "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_TASKS": str(tmp / "tasks.json"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:500] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


BAR = """() => { const b = document.getElementById('ftBar'); if (!b) return null;
  return { text: b.querySelector('.tp-actions').textContent, btns: [...b.querySelectorAll('.tp-actions .btn')].map((x) => [x.textContent, x.disabled]),
    items: b.querySelectorAll('.ft-list .ft-item').length, firstItem: (b.querySelector('.ft-list .ft-item') || {}).textContent || '',
    hits: [...b.querySelectorAll('.ft-list .ft-item-head .tp-tag')].filter((t) => t.textContent.startsWith('이 문서 ')).length }; }"""
TAGS = """() => { const rows = [...document.querySelectorAll('#tablesBox .tp-row')];
  return { rows: rows.length, tags: rows.map((r) => { const t = r.querySelector('.tp-forms .ft-tag'); return t ? t.textContent : ''; }),
    tip: ((rows.map((r) => r.querySelector('.tp-forms .ft-tag')).find(Boolean)) || {}).title || '' }; }"""
FIT = """() => { const p = document.getElementById('tablesBox'), r = p.getBoundingClientRect();
  const bad = [...p.querySelectorAll('#ftBar *')].filter(e => e.getClientRects().length && (e.getBoundingClientRect().right > r.right + 1 || e.getBoundingClientRect().left < r.left - 1))
    .slice(0, 6).map(e => e.className || e.tagName);
  return { bad, over: p.scrollWidth - p.clientWidth }; }"""

try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    r = requests.post(f"{base}/api/docs", files={"file": (RND.name, RND.read_bytes())}, timeout=120)
    r.raise_for_status()
    doc = r.json()["docId"]
    requests.post(f"{base}/api/docs/{doc}/headings", json={"stage": 3, "llm": False}, timeout=30).raise_for_status()
    for _ in range(600):
        j = requests.get(f"{base}/api/docs/{doc}/headings", timeout=30).json()
        if not (j.get("job") and j["job"]["status"] == "running"):
            break
        time.sleep(.5)
    v0 = requests.get(f"{base}/api/docs/{doc}/form-tables", timeout=60).json()
    check("서버 — 양식 연구개발계획서 · 등록부 없음 · 등록된 빈 양식(sha256)", v0.get("form", {}).get("key") == FORM and v0["registry"] is None and v0["missing"] == "registry"
          and v0["blank"] == "sha256", v0)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1700, "height": 1000})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("dialog", lambda d: (errors.append(f"dialog: {d.message}"), d.accept()))   # 확인 창은 쓰지 않는다 — 뜨면 오류로 센다
        page.goto(f"{base}/#w={doc}")
        page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=240000)
        page.wait_for_timeout(1500)
        undo0 = page.evaluate("() => state.undo || 0")

        # ---- 1. 등록부 없음
        page.evaluate("() => showTab('Tables')")
        page.wait_for_selector("#tablesBox .tp-row", timeout=60000)
        page.wait_for_selector("#ftBar", timeout=60000)
        b = page.evaluate(BAR)
        t = page.evaluate(TAGS)
        check("① 등록부 줄 — 「양식의 표 등록부 · 연구개발계획서 · 아직 없습니다」 + 「이 빈 양식으로 짓기」", b and "양식의 표 등록부" in b["text"] and FORM in b["text"] and "아직 없습니다" in b["text"]
              and ["이 빈 양식으로 짓기", False] in b["btns"], b)
        check("① 꼬리표 없음(등록부가 없다)", t["rows"] > 0 and not any(t["tags"]), t["tags"][:5])
        page.screenshot(path=str(OUT / "1_none.png"))

        # ---- 2. 짓기
        page.locator("#ftBar .btn:has-text('이 빈 양식으로 짓기')").click()
        page.wait_for_function("() => document.querySelectorAll('#tablesBox .tp-forms .ft-tag').length > 0", timeout=120000)
        page.wait_for_timeout(500)
        reg = requests.get(f"{base}/api/forms/{FORM}/tables", timeout=60).json()
        ids = [e["id"] for e in reg.get("tables") or ()]
        n3 = len(requests.get(f"{base}/api/docs/{doc}/headings", timeout=60).json()["stage3"]["tables"]) if requests.get(f"{base}/api/docs/{doc}/headings", timeout=60).json().get("stage3") else None
        check("② 서버에 등록부 — 항목이 있고 id 가 겹치지 않음 · 저장 파일 forms/연구개발계획서.tables.json", ids and len(set(ids)) == len(ids) and (tmp / "forms" / f"{FORM}.tables.json").is_file(),
              (len(ids), n3))
        b = page.evaluate(BAR)
        t = page.evaluate(TAGS)
        tagged = [x for x in t["tags"] if x]
        check("② 줄 — 「표 n · 서브 테이블 m · 스크립트 판정」 · 「이 문서: 이은 표 k/k」 · 「등록부 보기」 · 「이 빈 양식으로 다시 짓기」",
              b and f"표 {len(ids)}" in b["text"] and "스크립트 판정" in b["text"] and "이 문서: 이은 표" in b["text"] and ["등록부 보기", False] in b["btns"]
              and ["이 빈 양식으로 다시 짓기", False] in b["btns"], b)
        check("② 표마다 「양식 표」 꼬리표(확실함 — 「?」 없음)", tagged and all(x == "양식 표" for x in tagged), sorted(set(t["tags"])))
        check("② 꼬리표 풍선 도움말 — 소속 · 잇는 근거 · 병합 방식", "소속:" in t["tip"] and "잇는 근거: 소속 헤딩 · 차례" in t["tip"] and "병합 방식:" in t["tip"], t["tip"])
        page.screenshot(path=str(OUT / "2_built.png"))

        # ---- 3. 등록부 보기
        page.locator("#ftBar .btn:has-text('등록부 보기')").click()
        page.wait_for_function("() => document.querySelectorAll('#ftBar .ft-list .ft-item').length > 0", timeout=60000)
        b = page.evaluate(BAR)
        check("③ 펼친 등록부 — 항목 수 = 등록부 · 「이 문서 t…」 표지 · 「등록부 접기」", b["items"] == len(ids) and b["hits"] > 0 and ["등록부 접기", False] in b["btns"], {k: b[k] for k in ("items", "hits", "btns")})
        fit = page.evaluate(FIT)
        check("④ 패널 안에 들어감(가로 넘침 없음)", not fit["bad"] and fit["over"] <= 1, fit)
        page.screenshot(path=str(OUT / "3_list.png"))
        page.locator("#ftBar .btn:has-text('등록부 접기')").click()
        page.wait_for_function("() => !document.querySelector('#ftBar .ft-list')", timeout=30000)
        check("④ 문서를 안 바꿈(실행 취소 수 그대로)", page.evaluate("() => state.undo || 0") == undo0)
        browser.close()
    check("콘솔 오류 · 확인 창 없음", not errors, errors[:5])
finally:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
print(f"\n{'FAIL ' + str(len(fails)) if fails else 'ALL PASS'}")
sys.exit(1 if fails else 0)
