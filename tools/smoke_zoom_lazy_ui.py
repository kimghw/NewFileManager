"""배율 — 쪽 상자마다 · 보이는 쪽부터(spec_hwpx_웹편집 ② §2) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_zoom_lazy_ui.py <그림·임시 폴더> [--port 18179]

작은 문서(기술수요조사서 — 쪽 1개): 배율을 한 번에 바꾼다(뒤에서 도는 일 없음).
큰 문서(연구개발계획서 양식 — 쪽 74개): 배율이 #doc 이 아니라 쪽 상자마다 · 옛 방식(#doc 한 곳)과 배치가 같음 · 옆 열을 열면 보이는 쪽만 바로 바뀌고 나머지는 뒤에서 ·
바꾸는 동안 보기에 옛 배율 쪽이 그려지지 않음 · 창 가운데 자리 그대로 · 바꾸는 중 스크롤해도 보이는 쪽은 새 배율 · 자리 지키기 스크롤로는 오른쪽 단추 메뉴가 안 닫힘(사용자 스크롤은 닫음) ·
끝나면 묶어 둔 폭·가로 스크롤이 풀리고 쪽 여백 표시가 화면 크기 그대로 · −/+ · 폭/높이/여백 빼고 맞춤 · 2쪽 보기(한 번에) · 창 크기 · 콘솔 오류.
끝에 옆 열 열기·닫기 시간(첫 그리기 · 다 끝남)을 적는다(같이 도는 검사가 있으면 부푼다 — 한도는 넉넉히)."""
import argparse
import json
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
ap.add_argument("--port", type=int, default=18179)
args = ap.parse_args()
OUT = Path(args.out).resolve()
SMALL, BIG = "기술수요조사서.hwpx", "연구개발계획서_양식.hwpx"

OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"),
       "NFM_HEADINGS": str(tmp / "headings"), "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "PYTHONUTF8": "1"}
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
errors, fails = [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:500] if detail != "" and not ok else ""), flush=True)
    if not ok:
        fails.append(name)


def open_sample(page, name, timeout=240000):
    page.evaluate("() => { const s = document.getElementById('sampleSection'); s.hidden = false; s.open = true; }")
    page.evaluate("(n) => document.querySelector(`.sample[aria-label=\"예제 ${n} 열기\"]`).click()", name)
    page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=timeout)


FIRST_DONE = "() => typeof heads !== 'undefined' && heads.view && heads.view.stage2 && heads.view.stage3 && !(heads.view.job && heads.view.job.status === 'running')"
SETTLED = "() => !zoomJob.on && !zoomJob.timer"
FRAMES = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))"
# 쪽 상자들의 상태 — 목표 배율과 다른 쪽 수 · 그 가운데 보기에 걸친 수 · #doc 에 남은 것
STATE = """() => {
  const doc = document.getElementById('doc'), sc = document.getElementById('scroller'), o = sc.getBoundingClientRect(), z = state.zoom;
  let pend = 0, seen = 0;
  for (const k of doc.children) {
    if (+k.style.zoom === z) continue;
    pend += 1;
    const b = k.getBoundingClientRect();
    if (b.bottom > o.top && b.top < o.bottom) seen += 1;
  }
  return { n: doc.children.length, z, fit: state.fit, pend, seen, on: zoomJob.on, docZoom: doc.style.zoom, width: doc.style.width, ox: sc.style.overflowX, gap: doc.style.rowGap,
    hbar: sc.offsetHeight - sc.clientHeight > 4 }; // 가로 스크롤 막대가 보이는가(막대 높이만큼 보기가 줄어든다)
}"""
# 화면 자리(스크롤 상자 기준) — 쪽·문단·칸·표지·쪽 번호
SNAP = """() => {
  const sc = document.getElementById('scroller'), o = sc.getBoundingClientRect();
  const y0 = o.top - sc.scrollTop, x0 = o.left - sc.scrollLeft;
  const r = (e) => { const b = e.getBoundingClientRect(); return [b.left - x0, b.top - y0, b.width, b.height]; };
  const pick = (sel, n) => { const a = [...document.querySelectorAll(sel)], st = Math.max(1, Math.floor(a.length / n)), out = []; for (let i = 0; i < a.length; i += st) out.push(r(a[i])); return out; };
  return { sheets: [...document.querySelectorAll('#doc > *')].map(r), paras: pick('#doc .para', 500), tds: pick('#doc td', 500), marks: pick('#doc .tbl-mark', 200), labels: pick('#doc .sheet-label', 80),
    sw: sc.scrollWidth, sh: sc.scrollHeight };
}"""
CMP = """([a, b]) => {
  let mx = 0, n = 0;
  for (const k of ['sheets', 'paras', 'tds', 'marks', 'labels']) {
    if (a[k].length !== b[k].length) return { max: 9999, n: 0, why: `${k} 개수 ${a[k].length}/${b[k].length}` };
    for (let i = 0; i < a[k].length; i++) for (let j = 0; j < 4; j++) { mx = Math.max(mx, Math.abs(a[k][i][j] - b[k][i][j])); n += 1; }
  }
  return { max: Math.round(mx * 100) / 100, n, sw: [a.sw, b.sw], sh: [a.sh, b.sh] };
}"""
# 창 가운데 줄 근처의 문단 하나와 그 자리(가운데 줄에서의 거리 — 화면 px)
MIDPARA = """() => {
  const sc = document.getElementById('scroller'), o = sc.getBoundingClientRect(), mid = o.top + o.height / 2;
  let best = null, gap = Infinity;
  for (const p of document.querySelectorAll('#doc .para[data-id]')) {
    const b = p.getBoundingClientRect();
    if (b.bottom < o.top || b.top > o.bottom || !b.height) continue;
    const d = Math.abs((b.top + b.bottom) / 2 - mid);
    if (d < gap) { gap = d; best = p; }
  }
  if (!best) return null;
  const b = best.getBoundingClientRect();
  return { id: best.dataset.id, d: (b.top + b.bottom) / 2 - mid, z: state.zoom };
}"""
PARA_AT = """(id) => { const sc = document.getElementById('scroller'), o = sc.getBoundingClientRect(), p = document.querySelector(`#doc .para[data-id="${id}"]`), b = p.getBoundingClientRect();
  return { d: (b.top + b.bottom) / 2 - (o.top + o.height / 2), z: state.zoom }; }"""
# 표시(쪽 여백의 표 표지·「TN Lk」·손잡이)가 화면 크기 그대로인가 — 표시의 zoom × 쪽 배율 = 1
MARKS = """(onlySeen) => {
  const sc = document.getElementById('scroller'), o = sc.getBoundingClientRect();
  let n = 0, bad = 0, worst = 0;
  for (const s of document.querySelectorAll('#doc > .sheet')) {
    const b = s.getBoundingClientRect();
    if (onlySeen && (b.bottom < o.top || b.top > o.bottom)) continue;
    const z = +s.style.zoom;
    for (const m of s.children) { const mz = +m.style.zoom; if (!mz) continue; n += 1; const e = Math.abs(mz * z - 1); if (e > worst) worst = e; if (e > 0.01) bad += 1; }
  }
  return { n, bad, worst: Math.round(worst * 1000) / 1000 };
}"""
WATCH = """() => { // 프레임마다 — 배율을 뒤에서 바꾸는 동안 보기에 옛 배율 쪽이 걸쳐 있었던 프레임 수 · 스크롤 이벤트 수
  window.__zw = { frames: 0, bad: 0, scrolls: 0, stop: false };
  const sc = document.getElementById('scroller'), doc = document.getElementById('doc');
  sc.addEventListener('scroll', () => { if (zoomJob.on) window.__zw.scrolls += 1; }, { passive: true });
  const tick = () => {
    if (window.__zw.stop) return;
    if (zoomJob.on) {
      window.__zw.frames += 1;
      const o = sc.getBoundingClientRect(), z = state.zoom;
      for (const k of doc.children) { if (+k.style.zoom === z) continue; const b = k.getBoundingClientRect(); if (b.bottom > o.top + 1 && b.top < o.bottom - 1) { window.__zw.bad += 1; break; } }
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}"""

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
        page = browser.new_page(viewport={"width": 1700, "height": 1000})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("dialog", lambda d: d.accept())
        page.goto(base)
        page.wait_for_selector("#drop")

        def settle(timeout=120000):
            page.wait_for_function(SETTLED, timeout=timeout)
            page.evaluate(FRAMES)

        def timed(js, done):
            t0 = time.perf_counter()
            page.evaluate(js)
            page.wait_for_function(done, timeout=120000)
            page.evaluate(FRAMES)
            first = time.perf_counter() - t0
            st = page.evaluate(STATE)
            page.wait_for_function(SETTLED, timeout=120000)
            return round(first * 1000), round((time.perf_counter() - t0) * 1000), st

        OPEN, CLOSE = "() => { headsDlg('paras', '문단 목록', ''); }", "() => { headsColClose(true); }"
        SHOWN, GONE = "() => !document.getElementById('headsDlg').hidden", "() => document.getElementById('headsDlg').hidden"

        # ---- 1. 작은 문서 — 한 번에(뒤에서 도는 일 없음)
        open_sample(page, SMALL)
        page.wait_for_function(FIRST_DONE, timeout=120000)
        settle()
        s = page.evaluate(STATE)
        check("작은 문서: 배율이 쪽 상자에(#doc 에는 없음)", s["docZoom"] == "" and s["pend"] == 0 and s["n"] >= 1, s)
        z0 = s["z"]
        page.evaluate(OPEN)
        s = page.evaluate(STATE)  # 같은 일 안에서는 아직 배율이 안 바뀜(크기 감시가 다음 프레임에) — 그 뒤 두 프레임
        page.evaluate(FRAMES)
        s = page.evaluate(STATE)
        check("작은 문서: 옆 열을 열면 배율이 한 번에 바뀜(뒤에서 도는 일 없음)", s["z"] != z0 and s["pend"] == 0 and not s["on"] and s["width"] == "", s)
        page.evaluate(CLOSE)
        page.evaluate(FRAMES)
        s = page.evaluate(STATE)
        check("작은 문서: 닫으면 원래 배율", s["z"] == z0 and s["pend"] == 0 and not s["on"], s)
        page.evaluate("() => closeDoc()")
        page.wait_for_selector("#drop", state="visible")

        # ---- 2. 큰 문서(쪽 74개)
        open_sample(page, BIG)
        page.wait_for_function(FIRST_DONE, timeout=240000)
        page.wait_for_function("() => document.querySelectorAll('#doc .tbl-mark').length > 50", timeout=120000)
        settle()
        page.wait_for_timeout(1500)
        settle()
        s = page.evaluate(STATE)
        check("큰 문서: 쪽 상자 25개 이상", s["n"] > 24, s)
        check("배율이 쪽 상자마다(#doc 에는 없음) · 쪽 사이 간격 = 30 × 배율", s["docZoom"] == "" and s["pend"] == 0 and abs(float(s["gap"][:-2]) - 30 * s["z"]) < 0.02, s)
        check("다 바뀐 뒤 묶어 둔 폭·가로 스크롤이 풀려 있음", s["width"] == "" and s["ox"] == "" and not s["on"], s)
        zfit = s["z"]

        # 옛 방식(#doc 한 곳의 zoom)과 배치가 같은가 — 문서 가운데쯤에서
        page.evaluate("() => { const k = document.querySelectorAll('#doc > .sheet'); k[Math.floor(k.length / 2)].scrollIntoView({ block: 'start' }); }")
        page.wait_for_timeout(600)
        a = page.evaluate(SNAP)
        page.evaluate("() => { const doc = document.getElementById('doc'); for (const k of doc.children) k.style.zoom = ''; doc.style.rowGap = doc.style.columnGap = doc.style.paddingTop = ''; doc.style.zoom = state.zoom; void doc.offsetHeight; }")
        b = page.evaluate(SNAP)
        c = page.evaluate(CMP, [a, b])
        check("옛 방식(#doc 한 곳의 zoom)과 쪽·문단·칸·표지·쪽 번호 자리가 같음(0.5px 안)", c["max"] <= 0.5 and c["sw"][0] == c["sw"][1] and abs(c["sh"][0] - c["sh"][1]) <= 1, c)
        page.evaluate("() => { zoomApply(); }")
        settle()
        s = page.evaluate(STATE)
        check("되돌림: 다시 쪽 상자마다", s["docZoom"] == "" and s["pend"] == 0, s)
        a2 = page.evaluate(SNAP)
        c = page.evaluate(CMP, [a, a2])
        check("되돌린 뒤 자리 그대로", c["max"] <= 0.5, c)

        # 옆 열 열기 — 보이는 쪽만 바로, 나머지는 뒤에서 · 가운데 자리 그대로 · 보기에 옛 배율 쪽이 그려지지 않음
        page.evaluate(WATCH)
        m0 = page.evaluate(MIDPARA)
        check("보던 자리 준비: 창 가운데 근처에 문단이 있음", m0 is not None, page.evaluate(STATE))
        marks0 = page.evaluate(MARKS, False)
        first, total, st = timed(OPEN, SHOWN)
        t_open = (first, total)
        check("옆 열을 열면: 배율이 바뀌고, 첫 그리기 때 보기에 걸친 쪽은 모두 새 배율", st["z"] != zfit and st["seen"] == 0, st)
        check("옆 열을 열면: 나머지 쪽은 뒤에서(첫 그리기 때 아직 남아 있거나 방금 끝남) · 그동안 #doc 폭을 끝 폭으로 묶음", (st["on"] and st["pend"] > 0 and st["width"].startswith("max(")) or (not st["on"] and st["pend"] == 0), st)
        check("바꾸는 동안 가로 스크롤 막대가 생기지 않음(폭 맞춤)", not st["hbar"], st)
        s = page.evaluate(STATE)
        check("다 끝남: 모든 쪽이 새 배율 · 폭·가로 스크롤 풀림", s["pend"] == 0 and s["width"] == "" and s["ox"] == "" and s["docZoom"] == "", s)
        m1 = page.evaluate(PARA_AT, m0["id"])
        want = m0["d"] * m1["z"] / m0["z"]
        check("창 가운데 자리 그대로(가운데 문단이 배율 비만큼만 움직임 — 8px 안)", abs(m1["d"] - want) <= 8, {"before": m0, "after": m1, "want": round(want, 1)})
        w = page.evaluate("() => window.__zw")
        check("바꾸는 동안 보기에 옛 배율 쪽이 걸친 프레임 0", w["bad"] == 0, w)
        marks1 = page.evaluate(MARKS, False)
        check("끝난 뒤 쪽 여백 표시가 화면 크기 그대로(표시 zoom × 쪽 배율 = 1 — 개수는 배율 따라 한 줄에 모여 달라진다)", marks1["bad"] == 0 and marks0["bad"] == 0 and marks1["n"] > 0, {"before": marks0, "after": marks1})
        page.screenshot(path=str(OUT / "zoom_open.png"))

        # 닫기 — 첫 그리기 직후(뒤에서 도는 중)의 표시도 화면 크기 그대로(셈으로 맞춘 것)
        t0 = time.perf_counter()
        page.evaluate(CLOSE)
        page.wait_for_function(GONE)
        page.evaluate(FRAMES)
        first = round((time.perf_counter() - t0) * 1000)
        st = page.evaluate(STATE)
        mk = page.evaluate(MARKS, True)
        check("닫기: 첫 그리기 때 보기에 걸친 쪽은 모두 새 배율 · 보이는 표시는 화면 크기 그대로", st["z"] == zfit and st["seen"] == 0 and mk["bad"] == 0, {"st": st, "marks": mk})
        page.wait_for_function(SETTLED, timeout=120000)
        t_close = (first, round((time.perf_counter() - t0) * 1000))
        m2 = page.evaluate(PARA_AT, m0["id"])
        check("닫으면 가운데 문단이 처음 자리로(8px 안)", abs(m2["d"] - m0["d"]) <= 8, {"before": m0, "after": m2})
        a3 = page.evaluate(SNAP)
        c = page.evaluate(CMP, [a, a3])
        check("열고 닫은 뒤 배치가 처음과 같음(쪽·문단·칸·표지 — 1px 안)", c["max"] <= 1, c)

        # 바꾸는 중에 멀리 스크롤 — 보이는 쪽은 그리기 전에 새 배율
        page.evaluate(OPEN)
        page.wait_for_function(SHOWN)
        page.evaluate("() => new Promise((r) => requestAnimationFrame(r))")
        on = page.evaluate("() => zoomJob.on")
        page.evaluate("() => { const sc = document.getElementById('scroller'); sc.scrollTop = sc.scrollTop > sc.scrollHeight / 2 ? sc.scrollHeight * 0.12 : sc.scrollHeight * 0.85; }")
        page.evaluate(FRAMES)
        st = page.evaluate(STATE)
        check("바꾸는 중 멀리 스크롤해도 보기에 걸친 쪽은 새 배율", st["seen"] == 0, {"st": st, "wasOn": on})
        settle()
        w = page.evaluate("() => window.__zw")
        check("스크롤한 뒤에도 보기에 옛 배율 쪽이 걸친 프레임 0", w["bad"] == 0, w)
        mk = page.evaluate(MARKS, False)
        check("끝난 뒤 표시가 화면 크기 그대로(스크롤로 먼저 바꾼 쪽 포함)", mk["bad"] == 0, mk)

        # 자리 지키기 스크롤로는 오른쪽 단추 메뉴가 안 닫힘 · 사용자 스크롤은 닫음(문서 가운데 — 위쪽 쪽이 뒤에서 바뀐다)
        page.evaluate("() => { const sc = document.getElementById('scroller'); sc.scrollTop = sc.scrollHeight * 0.6; }")
        page.wait_for_timeout(400)
        s0 = page.evaluate("() => window.__zw.scrolls")
        page.evaluate(CLOSE)
        page.wait_for_function(GONE)
        page.evaluate(FRAMES)
        page.evaluate("() => { ctxOpen({ clientX: 300, clientY: 300 }, [['시험 항목', '', () => {}, false]]); }")
        opened = page.evaluate("() => !!ctx.menu && !ctx.menu.hidden")
        wason = page.evaluate("() => zoomJob.on")
        settle()
        page.wait_for_timeout(350)
        still = page.evaluate("() => !!ctx.menu && !ctx.menu.hidden")
        s1 = page.evaluate("() => window.__zw.scrolls")
        check("배율을 뒤에서 바꾸는 동안 연 오른쪽 단추 메뉴가 끝까지 열려 있음", opened and still, {"opened": opened, "still": still, "wasOn": wason, "scrolls": s1 - s0})
        page.evaluate("() => { document.getElementById('scroller').scrollTop += 240; }")
        page.evaluate(FRAMES)
        check("사용자 스크롤은 메뉴를 닫음", page.evaluate("() => !ctx.menu || ctx.menu.hidden"))

        # −/+ · 100% · 폭 맞춤
        page.evaluate("() => { const b = document.querySelector('#toolModes [data-tool=\"page\"]'); if (b) b.click(); }")
        m0 = page.evaluate(MIDPARA)
        if m0 is None:  # 그림만 있는 쪽 — 글이 있는 쪽으로
            page.evaluate("() => { document.querySelector('#doc .sheet-body > .para[data-id]').scrollIntoView({ block: 'center' }); }")
            page.wait_for_timeout(500)
            m0 = page.evaluate(MIDPARA)
        page.click("#zoomOut")
        page.click("#zoomOut")
        settle()
        s = page.evaluate(STATE)
        check("− 두 번: 손 배율 · 모든 쪽이 그 배율", s["fit"] is None and abs(s["z"] - (zfit - 0.2)) < 0.011 and s["pend"] == 0 and s["width"] == "", s)
        m1 = page.evaluate(PARA_AT, m0["id"])
        check("− 뒤 가운데 자리 그대로(8px 안)", abs(m1["d"] - m0["d"] * m1["z"] / m0["z"]) <= 8, {"before": m0, "after": m1})
        page.click("#zoomVal")
        settle()
        s = page.evaluate(STATE)
        check("배율 글: 100% · 쪽이 창보다 넓으면 가로 스크롤", s["z"] == 1 and s["pend"] == 0, s)
        mk = page.evaluate(MARKS, False)
        check("손 배율 뒤에도 표시가 화면 크기 그대로", mk["bad"] == 0, mk)
        page.click("#zoomFit")
        settle()
        s = page.evaluate(STATE)
        check("폭 맞춤: 처음 배율로 · 가로 스크롤 없음", s["fit"] == "width" and s["z"] == zfit and s["pend"] == 0 and not s["hbar"], s)

        # 높이 맞춤 · 여백 빼고 맞춤 — 보던 쪽이 창 맨 위에, 창 높이에 들어감
        for mode, top in (("height", 24), ("body", None)):
            page.click("#zoomHeight")
            settle()
            g = page.evaluate("""() => { const sc = document.getElementById('scroller'), o = sc.getBoundingClientRect(), s = viewSheet(sc, [...document.querySelectorAll('#doc > .sheet')]), b = s.getBoundingClientRect();
              return { fit: state.fit, z: state.zoom, top: Math.round(b.top - o.top), h: Math.round(b.height), room: Math.round(o.height), pend: [...document.getElementById('doc').children].filter((k) => +k.style.zoom !== state.zoom).length }; }""")
            ok = g["fit"] == mode and g["pend"] == 0 and (abs(g["top"] - top) <= 3 and g["h"] <= g["room"] if top is not None else g["top"] < 0)
            check(f"{'높이 맞춤' if mode == 'height' else '여백 빼고 맞춤'}: 보던 쪽이 창에 맞고 모든 쪽이 그 배율", ok, g)
        page.click("#zoomFit")
        settle()

        # 2쪽 보기 — 한 번에(격자 열 폭이 쪽 배율에 걸린다)
        page.click("#twoUp")
        page.evaluate(FRAMES)
        s = page.evaluate(STATE)
        two = page.evaluate("() => { const k = document.querySelectorAll('#doc > .sheet'); const a = k[0].getBoundingClientRect(), b = k[1].getBoundingClientRect(); return { sameTop: Math.abs(a.top - b.top) < 2, side: b.left > a.right, gap: Math.round((b.left - a.right) * 100) / 100, z: state.zoom }; }")
        check("2쪽 보기: 한 번에 바뀜 · 두 쪽이 나란히 · 사이 = 8 × 배율(가운데가 붙음)", s["pend"] == 0 and not s["on"] and two["sameTop"] and two["side"] and abs(two["gap"] - 8 * two["z"]) <= 0.6, {"st": s, "two": two})
        # 넓은 쪽(가로 구역)은 한 줄을 통째로(spec_hwpx_웹편집 ② §2 「2쪽 보기」 — 2026-11-18 사용자 「2페이지 보기면 최대한 가운데가 붙어 있고」: 열 폭이 가로 쪽을 따라 세로 쪽 사이가 벌어지던 것).
        # 예제에는 가로 구역이 없어 셋째 쪽 상자를 넓은 쪽으로 꾸며 본다(.span2 + 폭 1.4배) → 혼자 한 줄 · 가운데 · 앞뒤 줄의 두 쪽은 그대로 붙음. 구역 폭으로 고르는 셈(wideSecs)은 따로.
        wide = page.evaluate("""() => {
          const k = [...document.querySelectorAll('#doc > .sheet')], x = k[2], w0 = x.style.width;
          x.classList.add('span2'); x.style.width = `calc(${w0} * 1.4)`;
          const r = (e) => e.getBoundingClientRect(), d = r(document.getElementById('doc')), a = r(k[0]), b = r(k[1]), c = r(x), e4 = r(k[3]), e5 = r(k[4]);
          const out = { alone: c.top > a.bottom && e4.top > c.bottom, centered: Math.abs((c.left + c.right) / 2 - (a.right + b.left) / 2) <= 1.5, pair: Math.round((b.left - a.right) * 100) / 100,
            next: Math.abs(e4.top - e5.top) < 2 && Math.round((e5.left - e4.right) * 100) / 100, z: state.zoom, inDoc: c.left >= d.left - 1 };
          x.classList.remove('span2'); x.style.width = w0;
          const keep = state.sections; state.sections = [{ widthMm: 210 }, { widthMm: 297 }, { widthMm: 215.9 }, { widthMm: 420 }];
          out.secs = [...wideSecs()]; state.sections = [{ widthMm: 297 }, { widthMm: 297 }]; out.same = [...wideSecs()]; state.sections = keep;
          return out; }""")
        check("2쪽 보기: 넓은 쪽은 혼자 한 줄 · 두 열의 가운데 · 앞뒤 줄의 두 쪽은 그대로 붙음(사이 8 × 배율)",
              wide["alone"] and wide["centered"] and wide["inDoc"] and abs(wide["pair"] - 8 * wide["z"]) <= 0.6 and wide["next"] is not False and abs(wide["next"] - 8 * wide["z"]) <= 0.6, wide)
        check("넓은 구역 고르기 — 가장 좁은 용지보다 10% 넘게 넓은 구역만(A4 세로 · 가로 · Letter · A3 가로 → 가로 둘) · 모두 같은 폭이면 없음", wide["secs"] == [1, 3] and wide["same"] == [], wide)
        page.click("#twoUp")
        settle()
        s = page.evaluate(STATE)
        check("2쪽 보기 끔: 폭 맞춤 배율로 · 모든 쪽이 그 배율", s["z"] == zfit and s["pend"] == 0 and s["width"] == "", s)

        # 창 크기
        page.set_viewport_size({"width": 1300, "height": 900})
        page.evaluate(FRAMES)
        settle()
        s = page.evaluate(STATE)
        check("창을 줄이면 폭 맞춤 배율이 줄고 모든 쪽이 그 배율 · 가로 스크롤 없음", s["z"] < zfit and s["pend"] == 0 and not s["hbar"] and s["width"] == "", s)
        page.set_viewport_size({"width": 1700, "height": 1000})
        page.evaluate(FRAMES)
        settle()
        s = page.evaluate(STATE)
        check("창을 되돌리면 처음 배율", s["z"] == zfit and s["pend"] == 0, s)
        page.evaluate("() => { const k = document.querySelectorAll('#doc > .sheet'); k[Math.floor(k.length / 2)].scrollIntoView({ block: 'start' }); }")
        page.wait_for_timeout(600)
        a4 = page.evaluate(SNAP)
        c = page.evaluate(CMP, [a, a4])
        check("모두 거친 뒤 배치가 처음과 같음(1px 안)", c["max"] <= 1, c)
        page.evaluate("() => { window.__zw.stop = true; }")

        # 시간 — 옆 열 열기·닫기(첫 그리기 · 다 끝남). 옛 방식(문서 전체를 한 번에)은 이 문서에서 0.5~0.8초가 첫 그리기까지 멈췄다
        print(f"시간: 열기 첫 그리기 {t_open[0]} ms · 다 끝남 {t_open[1]} ms / 닫기 첫 그리기 {t_close[0]} ms · 다 끝남 {t_close[1]} ms", flush=True)
        check("옆 열 열기·닫기의 첫 그리기 1.5초 안(같이 도는 검사의 부하를 넉넉히 봄)", t_open[0] < 1500 and t_close[0] < 1500, {"open": t_open, "close": t_close})
        bad = [e for e in errors if "favicon" not in e]
        check("콘솔 오류 0", not bad, bad[:5])
        browser.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()

print(json.dumps({"fails": fails}, ensure_ascii=False))
sys.exit(1 if fails else 0)
