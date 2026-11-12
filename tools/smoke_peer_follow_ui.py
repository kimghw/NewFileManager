"""누른 자리 따라 보기(spec_작업 ② §12 「누른 자리 따라 보기」 · app/static/peer_follow.js) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_peer_follow_ui.py <그림·임시 폴더> [--port 18214]

작은 문서 둘(기술수요조사서.hwpx 두 번 — 블록 id 가 같다)을 한 과제의 이관(사업계획서·연차보고서)으로 묶는다. 원본 자리 지도(GET …/merge-links/origins)는 가짜 응답으로 끼운다
(진짜 지도는 tests/test_merge_origins.py — 여기서는 화면만): 연차보고서의 자리를 누르면 다른 면이 지도의 원본 자리로 가는지 · 문단 → 칸 → 표로 올라가는지 · 초점이 안 옮겨 가는지 ·
「따라 보기」 단추로 끄고 켜는지(기억) · 연차보고서가 둘째 면일 때 · 접힌 둘째 면 · 글만 고치면 지도를 다시 안 읽는지 · 끝점이 없는 서버(405)."""
import argparse
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
ap.add_argument("--port", type=int, default=18214)
args = ap.parse_args()
OUT = Path(args.out).resolve()
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
errors, fails, writes, asked = [], [], [], []
mode = {"map": {}, "status": 200}


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:300] if detail != "" else ""), flush=True)
    if not ok:
        fails.append(name)


def upload(name):
    return requests.post(f"{base}/api/docs?new=1", files={"file": (name, (ROOT / "samples" / name).read_bytes())}, timeout=120).json()["docId"]


def task(wid, file):
    requests.put(f"{base}/api/works/{wid}/task", json={"kind": "rnd", "file": file, "job": "plan_to_report", "project": "FOLLOW"}, timeout=10).raise_for_status()


def open_work(page, wid):
    page.evaluate("(id) => { location.hash = '#w=' + id; }", wid)
    page.reload()
    page.wait_for_function("(id) => state.id === id && document.querySelector('#doc .sheet .para') != null", arg=wid, timeout=120000)


def peek(page, wid):
    """둘째 면 화면(iframe)의 Frame — 그 문서가 그려지고 따라 보기 코드가 실릴 때까지."""
    page.wait_for_function("(id) => { try { const w = document.getElementById('peerFrame').contentWindow; return w.followPeekId() === id && !!w.document.querySelector('#doc .sheet .para'); } catch { return false; } }",
                           arg=wid, timeout=120000)
    return next(f for f in page.frames if f"peek={wid}" in f.url)


SEL = "() => ({ sel: state.selected, top: Math.round(document.getElementById('scroller').scrollTop), focus: (document.activeElement && document.activeElement.dataset || {}).id || '' })"
BTN = "() => { const b = document.getElementById('peerFollow'), r = b.getBoundingClientRect(); return { shown: !b.hidden && r.width > 0, on: b.classList.contains('on'), pressed: b.getAttribute('aria-pressed'), h: Math.round(r.height), title: b.title }; }"

try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    plan, report, lone = upload("기술수요조사서.hwpx"), upload("기술수요조사서.hwpx"), upload("기술수요조사서.hwpx")
    task(plan, "plan")
    task(report, "report")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1900, "height": 900})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" and "405" not in m.text else None)   # 옛 서버 흉내(405)의 브라우저 알림은 뺀다
        page.on("request", lambda r: writes.append(f"{r.method} {r.url}") if r.method != "GET" and "peek=" in (r.frame.url if r.frame else "") else None)

        def origins(route):   # 가짜 원본 자리 지도 — 정규식으로 끼운다(glob 은 하위 경로를 놓친다)
            asked.append(route.request.url)
            if mode["status"] != 200:
                route.fulfill(status=mode["status"], content_type="application/json", body='{"detail": "Method Not Allowed"}')
            else:
                route.fulfill(json={"to": {"work": report, "rev": 0}, "from": {"work": plan, "name": "기술수요조사서.hwpx", "rev": 0}, "reasons": [], "map": mode["map"], "counts": {}})
        page.route(re.compile(r"/api/docs/[^/]+/merge-links/origins"), origins)
        page.goto(base)
        open_work(page, report)
        fr = peek(page, plan)

        # 문서에서 쓸 자리(이 문서는 표 둘뿐 — 첫 표 3칸 · 둘째 표 40칸): 첫 표의 문단 A(문단 짝) · 짝 없는 문단 · 둘째 표의 칸(칸 짝) · 칸 짝이 없는 칸(표 짝) · 갈 자리 B(맨 아래)·가운데
        ids = page.evaluate("""() => {
          const by = {};
          for (const td of document.querySelectorAll('#doc td[data-cell]')) {
            const t = td.closest('table.tbl');
            if (!t.parentElement.closest('table.tbl') && td.querySelector('.para') && !td.querySelector('table')) (by[t.dataset.tbl] ||= []).push(td);
          }
          const keys = Object.keys(by), c1 = by[keys[0]], c2 = by[keys[1]], para = (td) => td.querySelector('.para').dataset.id;
          return { a: para(c1[0]), none: para(c1[c1.length - 1]), b: para(c2[c2.length - 1]), mid: para(c2[Math.floor(c2.length / 2)]),
            cell: c2[0].dataset.cell, cellPara: para(c2[0]), cell2: c2[1].dataset.cell, cell2Para: para(c2[1]), tbl: keys[1] };
        }""")
        mode["map"] = {ids["a"]: ids["b"], ids["cell"]: ids["mid"], ids["tbl"]: ids["a"]}
        page.wait_for_function("() => !!follow.map", timeout=20000)   # 둘째 면이 뜬 뒤 미리 읽는다
        n0 = len(asked)
        page.evaluate("() => followLoad(followPair())")   # 자리를 고른 뒤의 지도로 다시(미리 읽은 것은 빈 지도)
        page.wait_for_function("(a) => follow.map && !!follow.map[a]", arg=ids["a"])
        check("둘째 면이 뜨면 지도를 미리 읽음(목적 문서 = 연차보고서)", n0 >= 1 and all(f"/api/docs/{report}/merge-links/origins" in u for u in asked), asked[:3])

        # ---- 1. 단추 — 이관의 두 칸이 차 있으면 보이고, 기본 켬
        b = page.evaluate(BTN)
        check("「따라 보기」 단추 — 보임 · 켬(눌림) · 26px", b["shown"] and b["on"] and b["pressed"] == "true" and b["h"] == 26 and "이어진 자리 3곳" in b["title"], b)

        def click(pid, frame=page):
            frame.evaluate("(id) => paraEl(id).scrollIntoView({ block: 'center' })", pid)
            frame.click(f'#doc .para[data-id="{pid}"]')
            time.sleep(.9)

        # ---- 2. 연차보고서(첫째 면)의 자리를 누르면 둘째 면(사업계획서)이 원본 자리로 — 초점은 누른 문단에 그대로
        was = fr.evaluate(SEL)
        click(ids["a"])
        now, me = fr.evaluate(SEL), page.evaluate(SEL)
        check("문단을 누름 → 둘째 면이 지도의 원본 문단으로(스크롤)", now["sel"] == ids["b"] and now["top"] > was["top"], (was, now))
        check("초점은 누른 문단에 그대로(둘째 면이 초점을 안 가져감)", me["focus"] == ids["a"] and now["focus"] == "", (me, now))
        check("둘째 면의 그 문단이 깜빡임", fr.evaluate("(id) => paraEl(id).classList.contains('flash')", ids["b"]))
        click(ids["cellPara"])
        check("표 칸 안 문단 → 칸의 짝으로(문단 → 칸으로 올라감)", fr.evaluate(SEL)["sel"] == ids["mid"], fr.evaluate(SEL))
        click(ids["cell2Para"])
        check("칸 짝이 없는 칸 → 그 표의 짝으로(칸 → 표로 올라감)", ids["cell2"] != ids["cell"] and fr.evaluate(SEL)["sel"] == ids["a"], fr.evaluate(SEL))
        was = fr.evaluate(SEL)
        click(ids["none"])
        check("짝 없는 자리 → 아무 일 없음", fr.evaluate(SEL) == was, (was, fr.evaluate(SEL)))
        page.screenshot(path=str(OUT / "follow.png"))

        # ---- 3. 글만 고치면 지도를 다시 안 읽는다 · 문단 수가 달라지면 다시 읽는다
        n1 = len(asked)
        page.evaluate("(id) => { const p = paraEl(id); p.focus(); document.execCommand('insertText', false, '가'); }", ids["none"])
        page.wait_for_function("(id) => state.edited.has(id)", arg=ids["none"], timeout=20000)
        click(ids["a"])
        check("글만 고친 뒤 누름 — 지도를 다시 안 읽고 바로 감", len(asked) == n1 and fr.evaluate(SEL)["sel"] == ids["b"], (n1, len(asked)))
        page.evaluate("() => state.byId.set('__x', {})")   # 문단이 하나 늘어난 것 흉내(내용 반영·줄 넣기 뒤)
        click(ids["cellPara"])
        check("문단 수가 달라진 뒤 누름 — 가진 지도로 바로 가고 뒤에서 다시 읽음", len(asked) == n1 + 1 and fr.evaluate(SEL)["sel"] == ids["mid"], (n1, len(asked)))
        page.evaluate("() => state.byId.delete('__x')")
        page.wait_for_function("() => !follow.busy")

        # ---- 4. 끄기 · 켜기(기억)
        page.click("#peerFollow")
        b = page.evaluate(BTN)
        check("단추 = 끔(눌림 풀림 · 기억 off)", not b["on"] and b["pressed"] == "false" and page.evaluate("() => localStorage.getItem('nfm.peerFollow')") == "off", b)
        was = fr.evaluate(SEL)
        click(ids["a"])
        check("끈 동안 — 눌러도 둘째 면은 그대로", fr.evaluate(SEL) == was, (was, fr.evaluate(SEL)))
        page.click("#peerFollow")
        click(ids["a"])
        check("다시 켬 — 누르면 따라감(기억 on)", page.evaluate(BTN)["on"] and page.evaluate("() => localStorage.getItem('nfm.peerFollow')") == "on" and fr.evaluate(SEL)["sel"] == ids["b"])

        # ---- 5. 둘째 면을 띠로 접으면 안 따라간다(다시 펴지 않는다)
        click(ids["cellPara"])
        page.click("#peerFold")
        was = fr.evaluate(SEL)
        click(ids["a"])
        check("접힌 둘째 면 — 안 따라가고 접힌 채", fr.evaluate(SEL)["sel"] == was["sel"] and page.evaluate("() => document.getElementById('peerCol').classList.contains('folded')"), (was, fr.evaluate(SEL)))
        page.click("#peerRail")

        # ---- 6. 사업계획서를 고치는 문서로(연차보고서가 둘째 면) — 둘째 면의 연차보고서 자리를 누르면 첫째 면(사업계획서)이 원본 자리로 · 사업계획서를 누르면 아무 일 없음
        open_work(page, plan)
        fr2 = peek(page, report)
        page.wait_for_function("(a) => follow.map && !!follow.map[a]", arg=ids["a"], timeout=20000)
        was = page.evaluate(SEL)
        click(ids["a"], fr2)
        now = page.evaluate(SEL)
        check("둘째 면(연차보고서)의 자리를 누름 → 첫째 면(사업계획서)이 원본 자리로", now["sel"] == ids["b"] and now["top"] > was["top"], (was, now))
        was = fr2.evaluate(SEL)
        click(ids["cellPara"])
        check("사업계획서(원본)의 자리를 눌러도 연차보고서는 안 움직임", fr2.evaluate(SEL)["sel"] == was["sel"], (was, fr2.evaluate(SEL)))
        check("단추는 이 배치에서도 보임", page.evaluate(BTN)["shown"])

        # ---- 7. 이관이 아닌 문서 — 단추 없음(둘째 면도 없다)
        open_work(page, lone)
        check("이관이 아닌 문서 — 단추 숨김 · 누를 일 없음", page.evaluate("() => followPair() === null && document.getElementById('peerFollow').hidden"))

        # ---- 8. 끝점이 없는 서버(재시작 전 — 405): 한 번만 알리고 그만 묻는다, 화면 오류 없음
        mode["status"] = 405
        open_work(page, report)
        fr = peek(page, plan)
        page.wait_for_function("() => follow.missing === true", timeout=20000)
        n2 = len(asked)
        toast = page.evaluate("() => document.getElementById('toast').textContent")
        click(ids["a"])
        click(ids["cellPara"])
        check("끝점이 없으면 — 「서버를 다시 시작한 뒤」 한 번 알리고 더 안 묻는다", "다시 시작" in toast and len(asked) == n2 and "다시 시작" in page.evaluate(BTN)["title"], (toast, n2, len(asked)))

        check("둘째 면 화면이 보낸 GET 밖 요청 0", not writes, writes[:5])
        check("화면 오류 0", not errors, errors[:5])
        browser.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()

print(f"\n{'실패 ' + str(len(fails)) + '개: ' + ', '.join(fails) if fails else '모두 통과'}")
sys.exit(1 if fails else 0)
