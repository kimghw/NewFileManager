"""줄 앞 공백(spec_hwpx_웹편집 ② §3-4 「줄 앞 공백」 — app.js renderPara · leadWrap · leadFix · leadLeave, style.css .lead-sp) 화면 확인 —
임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(흉내 없음).

한글의 양쪽 정렬은 줄 안 빈칸만 늘리고 문단 첫머리의 들여쓰기용 빈칸은 그대로 둔다. 브라우저는 줄 앞 빈칸까지 늘려서 글이 둘째 줄로 넘어간 문단만
레터가 오른쪽으로 밀려 보였다(같은 서식인데 한 줄 문단과 자리가 다름). 첫머리 빈칸을 늘어나지 않는 조각(.lead-sp)으로 감싼 것을 본다.

기술수요조사서(작은 문서)의 양쪽 정렬 문단 p86 의 글을 「- 가나 다라 한한한…(긴 한 낱말) 끝말 …」 로 바꿔(낱말이 적어 첫 줄의 빈칸이 크게 늘어나는 여러 줄 문단)
화면에서 앞 공백 4칸을 쳐 넣고:
- 친 빈칸이 조각 안으로 · 글은 그대로 · 커서 자리 그대로.
- 첫 글자의 자리 = 왼쪽 정렬로 그렸을 때의 자리(= 한글의 자리 — 앞 공백이 안 늘어남) · 그 줄의 줄 안 빈칸은 늘어나 있음(양쪽 정렬은 살아 있음) ·
  조각을 풀면(옛 그리기) 첫 글자가 오른쪽으로 밀림(이 검사가 옛 동작을 잡는다는 확인) · 문단 높이는 그대로.
- 저장 → 새로 고침(서버가 준 글로 그림) → 같은 꼴 · 같은 자리.
- 편집: 조각 안에서 글자를 치면 조각 밖으로 · 지우면 되돌아옴 · 조각 가운데에 글자 → 앞 빈칸만 조각 · Backspace·빈칸 · 조각 끝에서 글자.
- 키: Home → End = 첫 줄 끝(조각 끝에 안 멈춤) · Shift+End = 첫 줄 고르기 · → 로 한 글자씩 · ↓ ↑ 로 줄을 오감 · 고른 글 = 문단 글(조각 경계에 줄 바꿈 없음).
- 한글 조합(IME — CDP): 조각 안에서 조합 → 끝난 뒤 조각 밖으로 · 글 순서 그대로.
- 양쪽 정렬이 아닌 문단에는 조각이 없다 · 콘솔 오류 없음.

    python -X utf8 tools/smoke_lead_space_ui.py <출력 폴더> [--port 18481]
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
ap.add_argument("--port", type=int, default=18481)
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
SRC = ROOT / "samples" / "기술수요조사서.hwpx"
PID = "p86"


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


# 문단의 꼴과 자리 — lead = 조각들의 글, x = 첫 글자(빈칸 아닌)의 왼쪽, xLeft = 왼쪽 정렬로 그렸을 때, xPlain = 조각을 풀었을 때(옛 그리기), gap = 첫 줄 줄 안 빈칸 폭들
LOOK = """(id) => { const p = paraEl(id), text = readText(p), n = text.length - text.replace(/^ +/, '').length;
  const at = (k) => { const [node, off] = pointAt(p, k + 1), r = document.createRange(); r.setStart(node, off - 1); r.setEnd(node, off); return r.getClientRects()[0]; };
  const x = () => Math.round(at(n).left * 100) / 100, y0 = at(n).top;
  const gaps = []; for (let k = n + 1; k < text.length && gaps.length < 40; k++) { if (text[k] !== ' ') continue; const b = at(k); if (!b || Math.abs(b.top - y0) > 3) break; gaps.push(Math.round(b.width * 100) / 100); }
  const leadW = n ? Math.round(at(0).width * 100) / 100 : 0;
  const now = x(), h = Math.round(p.getBoundingClientRect().height * 10) / 10, keep = p.style.textAlign;
  p.style.textAlign = 'left'; const xLeft = x(); p.style.textAlign = keep;
  const sps = [...p.querySelectorAll('.lead-sp')];
  for (const s of sps) s.style.display = 'inline'; const xPlain = x(), hPlain = Math.round(p.getBoundingClientRect().height * 10) / 10; for (const s of sps) s.style.display = '';
  let end1 = n; for (let k = n; k < text.length; k++) { const b = at(k); if (b && b.width > 0 && Math.abs(b.top - y0) > 3) break; end1 = k + 1; }
  return { text: text.slice(0, 14), len: text.length, n, lead: sps.map((s) => s.textContent).join(''), end1, x: now, xLeft, xPlain, h, hPlain, leadW, gaps: gaps.slice(0, 6), minGap: gaps.length ? Math.min(...gaps) : 0,
    lines: Math.round(p.getBoundingClientRect().height / parseFloat(getComputedStyle(p).lineHeight)), align: p.style.textAlign, caret: caretAt(p), nodes: p.querySelectorAll('.lead-sp').length }; }"""


def look(page, pid=PID):
    return page.evaluate(LOOK, pid)


def caret(page, k, pid=PID):
    page.evaluate("([id, k]) => { const p = paraEl(id); p.focus(); setCaret(p, k); }", [pid, k])
    page.wait_for_timeout(60)


def saved(page):
    page.evaluate("flushAll()")
    page.wait_for_function("() => !state.timers.size && !state.inflight", timeout=20000)


def main():
    wait_server()
    r = requests.post(base + "/api/docs", files={"file": (SRC.name, SRC.read_bytes(), "application/octet-stream")}, timeout=120)
    assert r.status_code == 200, r.text
    doc = r.json()["docId"]
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1500, "height": 950}, device_scale_factor=1)
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{base}/#w={doc}")
        page.wait_for_selector(f'#doc .para[data-id="{PID}"]', timeout=60000)
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(600)
        page.evaluate("(id) => paraEl(id).scrollIntoView({ block: 'center' })", PID)
        # 낱말이 적은 여러 줄 문단으로 — 긴 한 낱말 때문에 첫 줄에 빈칸이 몇 개뿐이라 빈칸 하나가 크게 늘어난다
        n = page.evaluate("(id) => { const p = paraEl(id), cs = getComputedStyle(p), sp = p.querySelector('span') || p; return Math.floor((p.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)) / parseFloat(getComputedStyle(sp).fontSize)) - 5; }", PID)
        page.evaluate("(id) => { const p = paraEl(id); p.focus(); const r = document.createRange(); r.selectNodeContents(p); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }", PID)
        page.keyboard.insert_text("- 가나 다라 " + "한" * n + " 끝말 " + "마무리 글 " * 6)
        page.wait_for_timeout(150)
        v0 = look(page)
        check("처음 — 양쪽 정렬 여러 줄 문단(첫 줄이 「- 가나 다라 …」 로 시작) · 앞 공백 없음 · 조각 없음", v0["align"] == "justify" and v0["lines"] >= 2 and v0["n"] == 0 and v0["nodes"] == 0 and v0["end1"] < v0["len"] and n > 12, [n, v0])

        # 화면에서 앞 공백 4칸
        caret(page, 0)
        page.keyboard.type("    ")
        page.wait_for_timeout(120)
        v = look(page)
        check("앞 공백 4칸을 치면 조각에 4칸 · 글은 「    - …」 · 커서 4", v["lead"] == "    " and v["n"] == 4 and v["len"] == v0["len"] + 4 and v["caret"] == 4, v)
        check("첫 글자의 자리 = 왼쪽 정렬로 그린 자리(앞 공백이 안 늘어남)", abs(v["x"] - v["xLeft"]) < 0.3, v)
        check("그 줄의 줄 안 빈칸은 늘어나 있다(양쪽 정렬은 그대로) — 앞 공백 한 칸보다 넓음", v["gaps"][0] > v["leadW"] + 2, v)
        check("조각을 풀면(옛 그리기) 첫 글자가 오른쪽으로 밀린다 — 이 검사가 옛 동작을 잡는다", v["xPlain"] - v["x"] > 5, v)
        check("문단 높이는 조각이 있으나 없으나 같다", v["h"] == v["hPlain"], v)
        page.screenshot(path=str(OUT / "lead_1_typed.png"))

        # 저장 → 새로 고침 = 서버가 준 글로 그림(renderPara)
        saved(page)
        page.reload()
        page.wait_for_selector(f'#doc .para[data-id="{PID}"]', timeout=60000)
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(600)
        page.evaluate("(id) => paraEl(id).scrollIntoView({ block: 'center' })", PID)
        w = look(page)
        check("저장 → 새로 고침 뒤에도 조각에 4칸(서버가 런을 나눠 주면 조각도 나뉜다 — 그림은 같음) · 같은 자리", w["lead"] == "    " and w["n"] == 4 and abs(w["x"] - w["xLeft"]) < 0.3 and w["xPlain"] - w["x"] > 5, w)
        srv = requests.get(f"{base}/api/docs/{doc}", timeout=30).json()
        blk = next((x for x in walk(srv["blocks"]) if x.get("id") == PID), {})
        check("서버 문서의 글 = 앞 공백 4칸 + 원래 글(조각은 글에 안 남음)", (blk.get("text") or "").startswith("    -") and len(blk.get("text") or "") == v0["len"] + 4, (blk.get("text") or "")[:20])

        # 편집 — 조각 안에서 글자
        caret(page, 0)
        page.keyboard.type("x")
        page.wait_for_timeout(120)
        a = look(page)
        check("조각 처음에서 글자를 치면 조각이 없어지고(첫머리가 빈칸이 아님) 글 「x    -」 · 커서 1", a["lead"] == "" and a["text"].startswith("x    -") and a["caret"] == 1, a)
        page.keyboard.press("Backspace")
        page.wait_for_timeout(120)
        a = look(page)
        check("지우면 조각이 되돌아온다 — 4칸 · 커서 0 · 자리 그대로", a["lead"] == "    " and a["caret"] == 0 and abs(a["x"] - a["xLeft"]) < 0.3, a)
        caret(page, 2)
        page.keyboard.type("y")
        page.wait_for_timeout(120)
        a = look(page)
        check("조각 가운데에 글자 → 앞 2칸만 조각 · 글 「  y  -」 · 커서 3", a["lead"] == "  " and a["text"].startswith("  y  -") and a["caret"] == 3, a)
        page.keyboard.press("Backspace")
        page.wait_for_timeout(120)
        a = look(page)
        check("그 글자를 지우면 다시 4칸 조각 · 커서 2", a["lead"] == "    " and a["caret"] == 2, a)
        caret(page, 4)
        page.keyboard.press("Backspace")
        page.wait_for_timeout(120)
        a = look(page)
        check("조각 끝에서 Backspace → 3칸 · 커서 3", a["lead"] == "   " and a["n"] == 3 and a["caret"] == 3, a)
        page.keyboard.type(" ")
        page.wait_for_timeout(120)
        a = look(page)
        check("빈칸을 치면 다시 4칸(조각 안) · 커서 4", a["lead"] == "    " and a["caret"] == 4, a)
        page.keyboard.type("z")
        page.wait_for_timeout(120)
        a = look(page)
        check("조각 끝에서 글자 → 조각은 4칸 그대로 · 글 「    z-」 · 커서 5", a["lead"] == "    " and a["text"].startswith("    z-") and a["caret"] == 5, a)
        page.keyboard.type(" ")
        page.wait_for_timeout(120)
        a = look(page)
        check("글자 뒤의 빈칸은 줄 안 빈칸 — 조각은 4칸 그대로 · 커서 6", a["lead"] == "    " and a["text"].startswith("    z -") and a["caret"] == 6, a)
        page.keyboard.press("Backspace")
        page.keyboard.press("Backspace")
        page.wait_for_timeout(120)
        a = look(page)
        check("되지우면 처음 꼴 — 4칸 조각 · 글 「    -」", a["lead"] == "    " and a["text"].startswith("    -") and a["len"] == v0["len"] + 4, a)

        # 키
        caret(page, 6)
        page.keyboard.press("Home")
        home = page.evaluate("(id) => caretAt(paraEl(id))", PID)
        page.keyboard.press("End")
        end = page.evaluate("(id) => caretAt(paraEl(id))", PID)
        check("Home = 줄 처음(0) → End = 첫 줄 끝(조각 끝 4 에 안 멈춤)", home == 0 and end in (a["end1"] - 1, a["end1"]), [home, end, a["end1"]])
        caret(page, 1)
        page.keyboard.press("Shift+End")
        sel = page.evaluate("(id) => selOffsets(paraEl(id))", PID)
        check("조각 안에서 Shift+End = 거기서 첫 줄 끝까지 고름", sel and sel["start"] == 1 and sel["end"] == end, sel)
        caret(page, 0)
        path = []
        for _ in range(7):
            page.keyboard.press("ArrowRight")
            path.append(page.evaluate("(id) => caretAt(paraEl(id))", PID))
        check("→ 는 조각 경계를 넘어 한 글자씩", path == [1, 2, 3, 4, 5, 6, 7], path)
        caret(page, 2)
        page.keyboard.press("ArrowDown")
        down = page.evaluate("(id) => caretAt(paraEl(id))", PID)
        page.keyboard.press("ArrowUp")
        up = page.evaluate("(id) => caretAt(paraEl(id))", PID)
        check("조각 안에서 ↓ = 둘째 줄로 · ↑ = 첫 줄로 되돌아옴", down > end and up <= end, [down, up, end])
        whole = page.evaluate("(id) => { const p = paraEl(id), r = document.createRange(); r.selectNodeContents(p); const s = getSelection(); s.removeAllRanges(); s.addRange(r); return [s.toString() === readText(p), s.toString().slice(0, 8)]; }", PID)
        check("문단을 다 고른 글 = 문단 글(조각 경계에 줄 바꿈·빈칸이 안 낌)", whole[0], whole)

        # 한글 조합(IME) — 조각 안에서 조합을 시작
        cdp = page.context.new_cdp_session(page)
        caret(page, 2)
        cdp.send("Input.imeSetComposition", {"text": "ㄱ", "selectionStart": 1, "selectionEnd": 1})
        cdp.send("Input.imeSetComposition", {"text": "가", "selectionStart": 1, "selectionEnd": 1})
        mid = look(page)
        cdp.send("Input.insertText", {"text": "가"})
        page.wait_for_timeout(200)
        a = look(page)
        check("조합 중에는 문단 노드를 안 옮긴다(조각 안에 그대로) · 글은 「  가  -」", mid["text"].startswith("  가  -") and mid["lead"] == "  가  ", mid)
        check("조합이 끝나면 조각은 앞 2칸만 · 글 「  가  -」 · 커서 3", a["lead"] == "  " and a["text"].startswith("  가  -") and a["caret"] == 3, a)
        cdp.send("Input.imeSetComposition", {"text": "나", "selectionStart": 1, "selectionEnd": 1})
        cdp.send("Input.insertText", {"text": "나"})
        page.wait_for_timeout(200)
        a = look(page)
        check("이어서 조합 → 「  가나  -」 · 조각 2칸 그대로", a["lead"] == "  " and a["text"].startswith("  가나  -") and a["caret"] == 4, a)
        page.keyboard.press("Backspace")
        page.keyboard.press("Backspace")
        page.wait_for_timeout(150)
        a = look(page)
        check("두 글자를 지우면 4칸 조각 · 자리 그대로", a["lead"] == "    " and abs(a["x"] - a["xLeft"]) < 0.3, a)
        saved(page)
        srv = requests.get(f"{base}/api/docs/{doc}", timeout=30).json()
        blk = next((x for x in walk(srv["blocks"]) if x.get("id") == PID), {})
        check("편집을 마친 뒤 서버 문서의 글 = 앞 공백 4칸 + 원래 글", (blk.get("text") or "").startswith("    -") and len(blk.get("text") or "") == v0["len"] + 4, (blk.get("text") or "")[:20])

        # 양쪽 정렬이 아닌 문단 — 조각을 만들지 않는다
        other = page.evaluate("""() => { const p = [...document.querySelectorAll('#doc .para')].find((x) => x.style.textAlign !== 'justify' && readText(x).trim().length > 3 && !x.dataset.label); return p ? p.dataset.id : null; }""")
        if other:
            page.evaluate("(id) => paraEl(id).scrollIntoView({ block: 'center' })", other)
            caret(page, 0, other)
            page.keyboard.type("  ")
            page.wait_for_timeout(120)
            o = page.evaluate("(id) => { const p = paraEl(id); return { n: p.querySelectorAll('.lead-sp').length, text: readText(p).slice(0, 6), align: p.style.textAlign }; }", other)
            check("양쪽 정렬이 아닌 문단은 앞 공백을 쳐도 조각이 없다(늘어날 일이 없음)", o["n"] == 0 and o["text"].startswith("  "), o)
            page.keyboard.press("Backspace")
            page.keyboard.press("Backspace")
            saved(page)
        else:
            check("양쪽 정렬이 아닌 문단을 찾음", False, "없음")
        page.screenshot(path=str(OUT / "lead_2_end.png"))
        b.close()
    check("콘솔 오류 없음", not errors, errors[:5])


def walk(blocks):
    for x in blocks:
        yield x
        if x.get("type") == "table":
            for c in x.get("cells", []):
                yield from walk(c.get("blocks", []))


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
