"""글 속 그림(spec_hwpx_웹편집 ② §3-6) 화면 확인 — 임시 서버(임시 작업 폴더, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright.

    python -X utf8 tools/smoke_text_pics_ui.py <그림·임시 폴더> [--port 18331]

글이 있는 문단에 글자처럼 취급으로 놓인 그림(글머리 아이콘 「▶ 제목」 — <run><pic/><t> 제목</t></run>)을 한글은 글과 같은 줄의 그 자리에 놓는다.
예제(기술수요조사서)에 그런 문단 둘을 만들어 올린다 — 표 칸 안의 것(칸의 첫 문단) · 본문의 것:
블록(pics · inlineOf) · 그림이 글 앞 같은 줄에(따로 한 줄을 차지하지 않음) · 블록 자리에는 빈 자리 표시 · 그림이 줄을 높이지 않음 ·
글을 고쳐도 그림이 남음(맨 앞에 치기 · 지우기 · 모두 고르고 치기 · 되돌리기) · 문단 나누기(Enter) 뒤에도 그림 · 다시 나눠도(paginate) 하나씩 · 콘솔 오류."""
import argparse
import copy
import io
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--port", type=int, default=18331)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)


def fixture() -> bytes:
    """예제에 글 속 그림 둘 — 본문 문단 「[그림] 본문의 글 속 그림 제목」(맨 끝) · 첫 표 첫 행 셋째 칸의 첫 문단 앞."""
    from lxml import etree

    from app.hwpx_doc import HP, HwpxDoc
    d = HwpxDoc((ROOT / "samples" / "기술수요조사서.hwpx").read_bytes())
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), "#e8590c").save(buf, "PNG")  # 16px = 4.2mm — 글 줄보다 낮은 아이콘
    iid = d.insert_image(d.blocks()[-1]["id"], buf.getvalue(), "png")
    pic = d._ids[iid]
    run = pic.getparent()
    for t in run.findall(f"{{{HP}}}t"):
        run.remove(t)
    etree.SubElement(run, f"{{{HP}}}t").text = " 본문의 글 속 그림 제목"
    cell = max((c for c in d.blocks()[0]["cells"] if (c["blocks"] and c["blocks"][0].get("text") or "").strip()), key=lambda c: c.get("widthMm") or 0)  # 넓은 칸 — 그림을 더해도 한 줄
    p = d._ids[cell["blocks"][0]["id"]]
    first = next(r for r in p.findall(f"{{{HP}}}run") if r.find(f"{{{HP}}}t") is not None)
    first.insert(0, copy.deepcopy(pic))
    for ls in p.findall(f"{{{HP}}}linesegarray"):
        p.remove(ls)
    return d.save()


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


def walk(blocks):
    for b in blocks:
        yield b
        for c in b.get("cells", ()):
            yield from walk(c["blocks"])


# 그 문단의 그림·글 자리(화면 px) — 그림 수 · 문단의 첫 자식이 그림인가 · 글의 줄 수 · 그림이 첫 글자와 같은 줄 · 그 앞인가 · 바로 뒤 블록 자리 표시
LOOK = """(pid) => {
  const p = document.querySelector(`#doc .para[data-id="${pid}"]`);
  if (!p) return null;
  const pics = [...p.querySelectorAll('.pic-in')], pic = pics[0] || null, box = p.getBoundingClientRect();
  const w = document.createTreeWalker(p, NodeFilter.SHOW_TEXT), r = document.createRange(), tops = new Set(); let first = null, n;
  while ((n = w.nextNode())) { // 글 노드만 — 줄 수는 글자 상자의 위끝으로 센다(그림 상자는 빼고)
    const i = n.data.search(/\\S/);
    if (i >= 0 && !first) first = [n, i];
    r.selectNodeContents(n);
    for (const x of r.getClientRects()) if (x.width > 0.5 && x.height > 2) tops.add(Math.round(x.top));
  }
  let g = null;
  if (first) { r.setStart(first[0], first[1]); r.setEnd(first[0], first[1] + 1); g = r.getBoundingClientRect(); }
  const pr = pic && pic.getBoundingClientRect(), td = p.closest('td');
  return { n: pics.length, firstIsPic: !!pic && p.firstChild === pic, lines: tops.size, text: readText(p),
    sameLine: !!(pr && g) && pr.top < g.bottom && pr.bottom > g.top, before: !!(pr && g) && pr.right <= g.left + 1,
    inBox: !!pr && pr.top >= box.top - 1.5 && pr.bottom <= box.bottom + 1.5, picH: pr ? pr.height : 0, paraH: box.height,
    held: !!p.nextElementSibling && p.nextElementSibling.classList.contains('pic-held'), tdH: td ? td.getBoundingClientRect().height : 0,
    editable: pic ? pic.contentEditable : '' };
}"""
# 그림을 감췄을 때의 문단·칸 높이(그림이 줄을 높이지 않는가)
BARE = """(pid) => {
  const p = document.querySelector(`#doc .para[data-id="${pid}"]`), pic = p.querySelector('.pic-in'), td = p.closest('td');
  pic.style.display = 'none';
  const out = { paraH: p.getBoundingClientRect().height, tdH: td ? td.getBoundingClientRect().height : 0 };
  pic.style.display = '';
  return out;
}"""
IDLE = "() => !state.busy && !state.inflight && !state.timers.size"

try:
    for _ in range(300):
        try:
            if requests.get(f"{base}/api/status", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(.2)
    else:
        raise RuntimeError("서버가 뜨지 않음")
    r = requests.post(f"{base}/api/docs", files={"file": ("글속그림.hwpx", fixture(), "application/octet-stream")}, timeout=120)
    r.raise_for_status()
    wid = r.json()["docId"]

    def server_blocks():
        return list(walk(requests.get(f"{base}/api/docs/{wid}", timeout=60).json()["blocks"]))

    bl = server_blocks()
    held = [b for b in bl if b.get("pics")]
    check("블록 — 글 속 그림이 있는 문단 둘(pics · at 0)", len(held) == 2 and all(len(b["pics"]) == 1 and b["pics"][0]["at"] == 0 for b in held), [(b["id"], b.get("pics")) for b in held])
    imgs = [b for b in bl if b.get("type") == "image"]
    check("블록 — 그 그림 블록은 그대로 있고 inlineOf 가 그 문단 · inlineRow 없음", len(imgs) == 2 and sorted(b.get("inlineOf") for b in imgs) == sorted(b["id"] for b in held)
          and all("inlineRow" not in b for b in imgs) and all(b["id"] == x["pics"][0]["id"] for b, x in zip(imgs, held)), imgs)
    top = next(b["id"] for b in requests.get(f"{base}/api/docs/{wid}", timeout=60).json()["blocks"] if b.get("pics"))
    cell = next(b["id"] for b in held if b["id"] != top)
    orig = {b["id"]: b["text"] for b in held}

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(viewport={"width": 1500, "height": 1000}).new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.goto(f"{base}/#w={wid}")
        page.wait_for_function("() => document.querySelector('#doc .sheet .para') != null", timeout=120000)
        page.wait_for_function("(id) => document.querySelector(`#doc .para[data-id=\"${id}\"] .pic-in`) != null", arg=top, timeout=30000)
        page.evaluate("() => document.fonts.ready")
        page.wait_for_timeout(500)

        for name, pid in (("표 칸", cell), ("본문", top)):
            page.evaluate("(id) => document.querySelector(`#doc .para[data-id=\"${id}\"]`).scrollIntoView({ block: 'center' })", pid)
            page.wait_for_timeout(300)
            a = page.evaluate(LOOK, pid)
            check(f"{name} — 그림이 문단 안 맨 앞에 하나 · 글 고치기 대상 아님(contenteditable=false)", a and a["n"] == 1 and a["firstIsPic"] and a["editable"] == "false", a)
            check(f"{name} — 그림이 첫 글자와 같은 줄 · 그 앞 · 글은 한 줄(그림이 줄을 따로 차지하지 않음)", a["sameLine"] and a["before"] and a["lines"] == 1 and a["inBox"], a)
            check(f"{name} — 블록 자리에는 빈 자리 표시(.pic-held)만 · 글은 그대로", a["held"] and a["text"] == orig[pid], a)
            b = page.evaluate(BARE, pid)
            check(f"{name} — 그림이 줄을 높이지 않음(그림을 감춘 높이와 같음)", abs(a["paraH"] - b["paraH"]) <= 0.5 and abs(a["tdH"] - b["tdH"]) <= 0.5, {"with": [a["paraH"], a["tdH"]], "bare": b})
            page.screenshot(path=str(OUT / f"{'cell' if pid == cell else 'top'}.png"))
        n = page.evaluate("() => [document.querySelectorAll('#doc .pic-in').length, document.querySelectorAll('#doc .pic-held').length, document.querySelectorAll('#doc img.img').length]")
        check("문서 — 글 속 그림 2 · 빈 자리 표시 2 · 따로 그린 그림 블록 0", n == [2, 2, 0], n)
        page.wait_for_function("(id) => { const i = document.querySelector(`#doc .para[data-id=\"${id}\"] .pic-in`); return i && i.complete && i.naturalWidth > 0; }", arg=cell, timeout=30000)
        check("그림 파일을 읽어 그림(naturalWidth > 0)", True)

        # ---- 글 고치기(표 칸의 문단 — 칸의 첫 문단이라 커서 0 의 Backspace 는 합칠 앞 문단이 없다 → 브라우저가 그림을 지우려 든다)
        para = page.locator(f'#doc .para[data-id="{cell}"]')
        para.scroll_into_view_if_needed()
        para.click()
        page.keyboard.press("Home")
        page.keyboard.type("가나")
        page.wait_for_timeout(200)
        a = page.evaluate(LOOK, cell)
        check("맨 앞에 글을 쳐도 그림이 맨 앞 · 친 글은 그림 뒤", a["n"] == 1 and a["firstIsPic"] and a["text"] == "가나" + orig[cell], a)
        c = page.evaluate("(id) => caretAt(document.querySelector(`#doc .para[data-id=\"${id}\"]`))", cell)
        check("커서는 친 글 뒤(2)", c == 2, c)
        page.keyboard.press("Backspace")
        page.keyboard.press("Backspace")
        page.wait_for_timeout(200)
        a = page.evaluate(LOOK, cell)
        check("친 글을 지우면 처음 글 · 그림 그대로", a["n"] == 1 and a["firstIsPic"] and a["text"] == orig[cell], a)
        page.keyboard.press("Backspace")  # 커서 0 — 글은 안 바뀌고 그림은 남는다
        page.wait_for_timeout(200)
        a = page.evaluate(LOOK, cell)
        check("커서 0 에서 Backspace — 그림이 지워지지 않음", a["n"] == 1 and a["firstIsPic"] and a["text"] == orig[cell], a)
        page.keyboard.press("Control+A")
        page.keyboard.type("새 제목")
        page.wait_for_timeout(200)
        a = page.evaluate(LOOK, cell)
        check("모두 고르고 쳐도 그림이 남음(맨 앞)", a["n"] == 1 and a["firstIsPic"] and a["text"] == "새 제목" and a["sameLine"] and a["before"], a)
        page.evaluate("() => flushAll()")
        page.wait_for_function(IDLE, timeout=30000)
        sb = next(b for b in server_blocks() if b["id"] == cell)
        check("서버 — 글만 바뀌고 그림은 그 자리(pics at 0)", sb["text"] == "새 제목" and [x["at"] for x in sb.get("pics") or []] == [0], sb)
        page.evaluate("(id) => revert(id)", cell)
        page.wait_for_function("([id, t]) => readText(document.querySelector(`#doc .para[data-id=\"${id}\"]`)) === t", arg=[cell, orig[cell]], timeout=30000)
        a = page.evaluate(LOOK, cell)
        check("되돌리기(문단을 다시 그림) 뒤에도 그림", a["n"] == 1 and a["firstIsPic"] and a["sameLine"] and a["before"], a)

        # ---- 구조 편집: 본문 문단 끝에서 Enter(문단 나누기) — 서버가 준 블록으로 다시 그려도 그림
        para = page.locator(f'#doc .para[data-id="{top}"]')
        para.scroll_into_view_if_needed()
        count = page.evaluate("() => document.querySelectorAll('#doc .para').length")
        para.click()
        page.keyboard.press("End")
        page.keyboard.press("Enter")
        page.wait_for_function("(n) => !state.busy && document.querySelectorAll('#doc .para').length === n + 1", arg=count, timeout=60000)
        a = page.evaluate(LOOK, top)
        check("문단 나누기(Enter) 뒤 — 앞 문단에 그림 하나 · 같은 줄", a and a["n"] == 1 and a["firstIsPic"] and a["sameLine"] and a["text"] == orig[top], a)
        sb = next(b for b in server_blocks() if b["id"] == top)
        check("서버 — 나눈 뒤에도 그 문단에 pics", [x["at"] for x in sb.get("pics") or []] == [0], sb)
        page.evaluate("() => paginate()")
        page.wait_for_timeout(300)
        n = page.evaluate("() => [document.querySelectorAll('#doc .pic-in').length, document.querySelectorAll('#doc .pic-held').length, document.querySelectorAll('#doc img.img').length]")
        check("쪽을 다시 나눠도(paginate) 그림은 하나씩", n == [2, 2, 0], n)
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
