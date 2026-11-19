"""표 서식 점검 · 맞추기(spec_헤딩_추출 ② §19 — 표 메뉴 「표 서식 점검…」) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_table_style_ui.py <그림·임시 폴더> [--port 18197]

연구개발계획서_양식.hwpx 를 API 로 올리고 「연구시설·장비」 표(t10834)의 값 칸을 표 채우기 반영 끝점으로 채워 빈 값 표시(「–」 셋 · 「-」 하나 · 빈 칸 하나)를 심는다 →
`#w=<id>` 로 열어 표 손잡이 → 표 메뉴의 「표 서식 점검…」(「서식으로 변환하기」 바로 뒤) → 2열 「표 서식 · t10834」(요약 · 빈 값 표시 줄 · 자리 묶음 · 확인 붙은 줄은 안 고름) →
줄에 올리면 문서의 그 칸 표시 → 보류된 헤더 지정(점검 응답에 held 를 얹어 — 요약 아래 한 줄 · 맞추기 단추 꺼짐: spec_테이블매니저 ② §3 「사람의 헤더 지정」) →
「고른 n곳 맞추기」(진짜 서버 — 요청에 rev · sigs · 「-」 칸이 「–」 · 실행 취소 1개 · 다시 점검해 그 줄이 빠짐) → 표지 표(t1)의 다른 서식 목록 · 열 폭 넘침 · 콘솔 오류."""
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
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--port", type=int, default=18197)
args = ap.parse_args()
OUT = Path(args.out).resolve()
RND = ROOT / "samples" / "연구개발계획서_양식.hwpx"
GRID = "t10834"

OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"),
       "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"), "NFM_JOBS": "off", "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "PYTHONUTF8": "1"}
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
    """표 칸을 눌러 고른 표로 만들고 손잡이를 눌러 표 메뉴를 연다."""
    page.locator(f"#doc table.tbl[data-tbl='{tid}'] td .para").first.scroll_into_view_if_needed()
    page.wait_for_timeout(1500)
    page.locator(f"#doc table.tbl[data-tbl='{tid}'] td .para").first.click()
    page.wait_for_selector(f".tbl-corner[data-for='{tid}']")
    page.locator(".tbl-corner").click()
    page.wait_for_selector(".ctx-menu[data-by='tmn']:not([hidden])")


VIEW = """() => { const w = document.querySelector('.tst-wrap'); if (!w) return null;
  const rows = [...w.querySelectorAll('table.tst-list tr')].filter((tr) => tr.querySelector('input')).map((tr) => ({
    ref: tr.querySelector('.hlink').textContent, on: tr.querySelector('input').checked, check: !!tr.querySelector('.hb.und'),
    text: tr.querySelector('.tst-text').textContent, diff: tr.querySelector('.tst-diff').textContent }));
  const held = w.querySelector('.tst-held'), btn = w.querySelector('.tst-bar .btn.primary');
  return { title: document.getElementById('headsDlgTitle').textContent, kind: heads.dlg, sum: w.querySelector('.tst-sum').textContent,
    empty: w.querySelector('.tst-empty').textContent, places: [...w.querySelectorAll('.tst-place > summary b')].map((b) => b.textContent),
    held: held && !held.hidden ? held.textContent : '', source: (w.querySelector('.ta-ident .hb') || {}).title || '',
    btn: (btn || {}).textContent || '', btnOff: !!(btn && btn.disabled), rows }; }"""
HELD_ON = "() => { const h = document.querySelector('.tst-wrap .tst-held'); return !!h && !h.hidden; }"
HELD_OFF = "() => { const h = document.querySelector('.tst-wrap .tst-held'); return !!h && h.hidden && !!document.querySelector('.tst-wrap .tst-list'); }"
FIT = """() => { const p = document.getElementById('headsDlg'), r = p.getBoundingClientRect();
  const bad = [...p.querySelectorAll('.tst-wrap *')].filter(e => e.getClientRects().length && (e.getBoundingClientRect().right > r.right + 1 || e.getBoundingClientRect().left < r.left - 1)).slice(0, 6).map(e => e.className || e.tagName);
  return { width: Math.round(r.width), bad, bodyOver: document.getElementById('headsDlgBody').scrollWidth - document.getElementById('headsDlgBody').clientWidth }; }"""


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
    blocks = requests.get(f"{base}/api/docs/{doc}", timeout=120).json()["blocks"]
    cover = next(b["id"] for b in blocks if b.get("type") == "table" and b.get("nRows", 0) > 20)   # 표지 표(첫 큰 표)

    def find(bs, tid):
        for b in bs:
            if b.get("type") == "table":
                if b["id"] == tid:
                    return b
                for c in b.get("cells") or []:
                    hit = find(c.get("blocks") or [], tid)
                    if hit:
                        return hit
        return None
    grid = find(blocks, GRID)
    check("견본의 「연구시설·장비」 표", grid is not None and grid["nRows"] == 7, grid and (grid["nRows"], grid["nCols"]))
    vals = sorted((c for c in grid["cells"] if c["row"] >= 1 and c["col"] >= 1), key=lambda c: (c["row"], c["col"]))
    pool = [c for c in vals if c["col"] >= 4]
    dash, hyphen, blank = pool[0:3], pool[4], pool[6]
    fills = [{"cell": c["id"], "text": "–" if c in dash else "-" if c is hyphen else f"값{i}"} for i, c in enumerate(vals) if c is not blank]
    fr = requests.post(f"{base}/api/docs/{doc}/tables/{GRID}/fill/apply", json={"fills": fills}, timeout=120)
    check("값 칸 채우기(표 채우기 반영 끝점) — 빈 값 표시 심기", fr.status_code == 200, fr.text[:300])
    sv = requests.get(f"{base}/api/docs/{doc}/tables/{GRID}/style", timeout=120).json()
    check("서버 점검 — 표시 「–」 · 「-」 칸 맞추기 · 빈 칸 하나는 확인", sv["empty"]["mark"] == "–" and sv["empty"]["fillBlanks"] and sv["empty"]["blanks"] == 1, sv["empty"])

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1700, "height": 1000})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/#w={doc}")
        page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=240000)
        page.wait_for_timeout(1500)

        # ---- 1. 표 메뉴의 새 항목
        corner(page, GRID)
        texts = [x["text"] for x in menu(page)]
        dis = {x["text"]: x["disabled"] for x in menu(page)}
        check("표 메뉴 — 「표 서식 점검…」 이 켜져 있고 「서식으로 변환하기」 바로 뒤", dis.get("표 서식 점검…") is False
              and texts.index("표 서식 점검…") == next(i for i, t in enumerate(texts) if t.startswith("서식으로 변환하기")) + 1, texts)
        page.screenshot(path=str(OUT / "1_menu.png"))
        page.locator(".ctx-menu[data-by='tmn'] button:has-text('표 서식 점검')").first.click()
        page.wait_for_selector(".tst-wrap .tst-list")
        page.wait_for_timeout(300)

        # ---- 2. 2열 — 요약 · 빈 값 표시 · 자리 · 줄
        v = page.evaluate(VIEW)
        check("2열 「표 서식 · t10834」(kind tblStyle)", v["title"] == f"표 서식 · {GRID}" and v["kind"] == "tblStyle", v["title"])
        check("빈 값 표시 줄 — 「–」 · 빈 칸 1(확인)", v["empty"].startswith("빈 값 표시 「–」") and "빈 칸 1(표시를 넣을지 확인)" in v["empty"], v["empty"])
        mk = next((x for x in v["rows"] if "빈 값 표시 지금 「-」 → 대표 「–」" in x["diff"]), None)
        bk = next((x for x in v["rows"] if "빈 칸 → 대표 「–」" in x["diff"]), None)
        check("「-」 줄은 고른 채 · 빈 칸 줄은 「확인」 이고 안 고름", mk and mk["on"] and not mk["check"] and bk and bk["check"] and not bk["on"], v["rows"])
        check("자리 묶음에 「빈 값」 · 맞추기 단추 글", "빈 값" in v["places"] and v["btn"].startswith("고른 ") and v["btn"].endswith("곳 맞추기"), (v["places"], v["btn"]))
        fit = page.evaluate(FIT)
        check("열 안에 들어감(가로 넘침 없음)", not fit["bad"] and fit["bodyOver"] <= 1, fit)
        page.screenshot(path=str(OUT / "2_grid.png"))

        # ---- 3. 줄에 올리면 문서의 그 칸 표시
        row = page.locator(".tst-list tr", has=page.locator(f".hlink:text-is('{mk['ref']}')")).first
        row.hover()
        hit = page.evaluate("() => document.querySelectorAll('#doc td.tst-hit').length")
        check("줄에 올리면 문서의 그 칸에 표시(td.tst-hit)", hit >= 1, hit)
        page.mouse.move(5, 5)
        # 첫 분석(스크립트)이 그새 끝났으면 「표 구조 결과」, 아니면 「초안」 + 표 구조 결과를 못 쓴 까닭 — 어느 쪽이든 풍선 도움말이 출처를 말한다
        check("칸 역할의 출처가 풍선 도움말에(초안이면 표 구조 결과를 못 쓴 까닭도) · 보류 줄 없음",
              (("스크립트 초안" in v["source"] and "까닭: " in v["source"]) or "표 구조(3단계) 결과" in v["source"]) and not v["held"], (v["source"], v["held"]))

        # ---- 3-1. 보류된 헤더 지정 — 점검 응답에 held 를 얹어 본다(서버 상태는 안 건드림): 요약 아래 한 줄 · 맞추기 단추 꺼짐
        style_url = re.compile(rf"/api/docs/[^/]+/tables/{GRID}/style$")

        def with_held(route):
            resp = route.fetch()
            if route.request.method != "GET" or resp.status != 200:
                return route.fulfill(response=resp)
            body = resp.json()
            body["held"] = [{"cell": hyphen["id"], "role": "rowhead", "why": "글이 바뀜"}]
            route.fulfill(response=resp, json=body)
        page.route(style_url, with_held)
        page.locator(".tst-wrap .ta-row button:text-is('다시 점검')").click()
        page.wait_for_function(HELD_ON, timeout=60000)
        vh = page.evaluate(VIEW)
        check("보류 줄 — 「헤더 지정 1칸이 지금 표와 맞지 않습니다 …」 · 맞추기 단추 꺼짐(고른 것이 있어도)",
              vh["held"].startswith("헤더 지정 1칸이 지금 표와 맞지 않습니다 — 표 메뉴에서 다시 지정하거나 풀어 주세요") and vh["btnOff"] and any(x["on"] for x in vh["rows"]), (vh["held"], vh["btn"], vh["btnOff"]))
        fit = page.evaluate(FIT)
        check("보류 줄 — 열 안에 들어감", not fit["bad"] and fit["bodyOver"] <= 1, fit)
        page.screenshot(path=str(OUT / "2_held.png"))
        page.unroute(style_url, with_held)
        page.locator(".tst-wrap .ta-row button:text-is('다시 점검')").click()
        page.wait_for_function(HELD_OFF, timeout=60000)
        page.wait_for_timeout(300)
        check("보류가 없으면 그 줄이 없고 맞추기 단추가 다시 켜짐", not page.evaluate(VIEW)["held"] and not page.evaluate(VIEW)["btnOff"], page.evaluate(VIEW)["btn"])

        # ---- 4. 맞추기 — 고른 것만 · 실행 취소 1개 · 다시 점검
        sent = []
        page.on("request", lambda q: sent.append(json.loads(q.post_data or "{}")) if q.method == "POST" and q.url.endswith("/style/apply") else None)
        undo0 = page.evaluate("() => state.undo")
        page.evaluate("() => { for (const tr of document.querySelectorAll('.tst-list tr')) { const cb = tr.querySelector('input'); if (!cb) continue; const want = tr.querySelector('.tst-diff').textContent.includes('빈 값 표시 지금 「-」'); if (cb.checked !== want) cb.click(); } }")
        v1 = page.evaluate(VIEW)
        check("「-」 줄 하나만 고름", v1["btn"] == "고른 1곳 맞추기", v1["btn"])
        page.locator(".tst-bar .btn.primary").click()
        page.wait_for_function("() => { const w = document.querySelector('.tst-wrap'); return w && !w.querySelector('.tst-diff') || [...document.querySelectorAll('.tst-diff')].every((e) => !e.textContent.includes('지금 「-」')); }", timeout=60000)
        page.wait_for_timeout(500)
        v2 = page.evaluate(VIEW)
        after = page.evaluate("(c) => ({ text: (document.querySelector(`#doc td[data-cell='${c}']`) || {}).textContent || '', undo: state.undo })", hyphen["id"])
        check("문서의 「-」 칸이 「–」 · 실행 취소 1개", after["text"].strip() == "–" and after["undo"] == undo0 + 1, (after, undo0))
        check("맞추기 요청 — 점검의 rev 와 고른 항목의 sig 를 같이 보냄", len(sent) == 1 and isinstance(sent[0].get("rev"), int) and len(sent[0].get("keys") or []) == 1
              and list(sent[0].get("sigs") or {}) == sent[0]["keys"] and all(isinstance(x, str) and x for x in sent[0]["sigs"].values()), sent)
        check("다시 점검 — 그 줄이 빠지고 빈 칸 줄(확인)은 남음", not any("지금 「-」" in x["diff"] for x in v2["rows"]) and any("빈 칸 → 대표 「–」" in x["diff"] for x in v2["rows"]), v2["rows"])
        page.screenshot(path=str(OUT / "3_after.png"))

        # ---- 5. 표지 표 — 다른 서식(글꼴 · 크기 · 여백) 목록
        page.evaluate("(t) => tblStyleView(t)", cover)
        page.wait_for_function("(t) => document.getElementById('headsDlgTitle').textContent === `표 서식 · ${t}` && document.querySelector('.tst-wrap .tst-sum')?.textContent", arg=cover, timeout=60000)
        page.wait_for_timeout(300)
        v3 = page.evaluate(VIEW)
        # 표지 표는 서브 테이블이 여럿이다 — 자리 이름에 「 · 표 N」 이 붙는다(2026-11-19 부터 초안 판정도 띠를 지닌다: spec_테이블매니저 ② §2 「지금 판정」 — 전에는 3단계 결과가 있을 때만 서브 테이블마다 갈랐다)
        check("표지 표 — 머리열 · 머리행 자리 · 「지금 → 대표」 글 · 확인 줄은 안 고름", any(p.startswith("머리행") for p in v3["places"]) and any(p.startswith("머리열") for p in v3["places"])
              and all(" → 대표 " in x["diff"] for x in v3["rows"]) and all(not x["on"] for x in v3["rows"] if x["check"]) and any(x["check"] for x in v3["rows"]), (v3["places"], v3["rows"][:4]))
        fit = page.evaluate(FIT)
        check("표지 표 — 열 안에 들어감", not fit["bad"] and fit["bodyOver"] <= 1, fit)
        page.screenshot(path=str(OUT / "4_cover.png"))
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
