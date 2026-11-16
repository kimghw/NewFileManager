"""hwpx 공유(spec_공유 — app/share.py · app/share_api.py · app/static/share.js · app/static/share/) 화면 확인 —
임시 서버(임시 작업 폴더 · 임시 공유 기록, PDF·LLM 끔)를 스스로 띄우고 끈다 + Playwright. 끝점은 모두 진짜(주인 = 임시 서버의 화면 · 손님 = 그 프로세스가 연 공유 포트의 화면).

주인 화면에서 기술수요조사서(hwpx)를 열고:
- 상단 바 「공유」 단추 → 떠 있는 창(모달 아님 · 화면 안 · 넘침 없음) → 공유폴더·이름을 넣고 「공유 켜기」 → 링크·키가 보이고 저장본·링크 바로가기가 공유폴더에 생긴다.
- 손님(다른 브라우저 컨텍스트)이 링크로: 키 넣기 화면(문서는 안 보임) → 틀린 키는 거절 → 맞는 키로 문서가 보인다. 손님 화면은 /s/ · /share-static/ 밖으로 요청하지 않는다.
- 손님이 쓴 글이 주인 화면에 · 주인이 쓴 글이 손님 화면에(몇 초 안) · 손님이 작성 중인 문단은 주인 화면에서 못 고친다(색 띠) · 반대도.
- 손님의 Enter(줄 나누기)·Backspace(합치기)가 주인 화면에 그 블록만 반영 · 주인의 실행 취소는 손님 화면이 문서를 다시 읽어 맞춘다.
- 바뀐 문서는 조용해지면 공유폴더의 파일에 다시 쓴다 · 키를 새로 만들면 손님은 키 넣기로 돌아간다 · 공유를 끄면 손님 화면은 「공유가 끝났습니다」, 링크 바로가기는 지워지고 저장본은 남고 공유 포트는 닫힌다.
- 콘솔 오류 없음(손님 화면의 CSP 위반 포함).

    python -X utf8 tools/smoke_share_ui.py <출력 폴더> [--port 18490]      공유 포트 = 포트 + 700
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
ap.add_argument("--port", type=int, default=18490)
args = ap.parse_args()
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / "srv"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)
FOLDER = tmp / "SharePoint 공유"
FOLDER.mkdir()
SHARE_PORT = args.port + 700
env = {**os.environ, "NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": str(tmp / "works"), "NFM_RENDER": str(tmp / "render"), "NFM_HEADINGS": str(tmp / "headings"),
       "NFM_FORMS": str(tmp / "forms"), "NFM_DIVISION_PRESETS": str(tmp / "presets.json"), "NFM_STYLES": str(tmp / "styles"), "NFM_AGENTS": str(tmp / "agents.json"),
       "NFM_SHARE_PORT": str(SHARE_PORT), "NFM_SHARE_HOST": "127.0.0.1", "PYTHONUTF8": "1"}
env.pop("NFM_SHARES", None)
env.pop("NFM_SHARE_URL", None)
log = (OUT / "server.log").open("w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                        stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
base = f"http://127.0.0.1:{args.port}"
fails, host_err, guest_err, guest_req = [], [], [], []
NAME = "기술수요조사서.hwpx"


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


def until(page, js, arg=None, timeout=8000):
    """그 조건이 될 때까지 기다린다 → 됐는가."""
    try:
        page.wait_for_function(js, arg=arg, timeout=timeout)
        return True
    except Exception:  # noqa: BLE001
        return False


TEXT = "(id) => { const p = document.querySelector(`.para[data-id=\"${id}\"]`); return p ? p.innerText : null; }"
HAS = "([id, s]) => { const p = document.querySelector(`.para[data-id=\"${id}\"]`); return !!p && p.innerText.includes(s); }"
PARAS = "() => document.querySelectorAll('#doc .para').length"


def main():
    wait_server()
    doc = requests.post(base + "/api/docs?new=1", files={"file": (NAME, (ROOT / "samples" / NAME).read_bytes(), "application/octet-stream")}, timeout=120).json()["docId"]
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        hctx = b.new_context(viewport={"width": 1500, "height": 900})
        hctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
        host = hctx.new_page()
        host.on("console", lambda m: host_err.append(m.text) if m.type == "error" else None)
        host.on("pageerror", lambda e: host_err.append(str(e)))
        host.on("dialog", lambda d: d.accept())
        host.goto(f"{base}/#w={doc}")
        host.wait_for_function("(id) => state.id === id && !!document.querySelector('#doc .para')", arg=doc, timeout=120000)

        # ---- 단추 · 떠 있는 창 · 공유 켜기
        check("상단 바에 「공유」 단추가 「저장」 앞에 보인다", until(host, "() => { const b = document.getElementById('shareBtn'); return !!b && !b.hidden && b.textContent.trim() === '공유' && b.nextElementSibling.id === 'downloadBtn'; }"))
        host.click("#shareBtn")
        check("누르면 떠 있는 창 — 모달이 아니다", until(host, "() => !!document.getElementById('sharePop') && !document.querySelector('dialog[open]') && document.getElementById('shareBtn').getAttribute('aria-expanded') === 'true'"))
        box = host.evaluate("() => { const r = document.getElementById('sharePop').getBoundingClientRect(), p = document.getElementById('sharePop'); return { l: r.left, r: r.right, t: r.top, b: r.bottom, w: r.width, over: p.scrollWidth > p.clientWidth + 1, vw: innerWidth, vh: innerHeight, hs: [...p.querySelectorAll('input, .btn')].map((e) => Math.round(e.getBoundingClientRect().height)) }; }")
        check("창이 화면 안 · 폭 360 이하 · 가로 넘침 없음 · 입력·단추 28px", box["l"] >= 0 and box["r"] <= box["vw"] and box["b"] <= box["vh"] and box["w"] <= 361 and not box["over"] and set(box["hs"]) == {28}, box)
        host.click("#sharePop .share-acts .btn.primary")
        check("폴더를 안 넣으면 켜지 않는다", until(host, "() => document.getElementById('toast').textContent.includes('공유폴더 경로')") and not list(FOLDER.iterdir()))
        host.fill("#shareFolder", str(FOLDER))
        host.fill("#shareHost", "김주인")
        host.click("#sharePop .share-acts .btn.primary")
        check("켜면 링크와 키가 보인다", until(host, "() => !!document.getElementById('shareLink') && !!document.getElementById('shareKey')", timeout=20000))
        link, key = host.input_value("#shareLink"), host.input_value("#shareKey")
        check("링크는 공유 포트의 /s/<id> · 키는 XXXX-XXXX-XXXX", link.startswith(f"http://127.0.0.1:{SHARE_PORT}/s/") and len(key) == 14 and key[4] == key[9] == "-", (link, key))
        files = sorted(p.name for p in FOLDER.iterdir())
        first = (FOLDER / NAME).read_bytes() if (FOLDER / NAME).exists() else b""
        check("공유폴더에 저장본과 링크 바로가기", files == ["기술수요조사서 같이 쓰기.url", NAME] and first[:2] == b"PK" and (FOLDER / files[0]).read_text("utf-8").strip().endswith(link), files)
        check("단추가 「공유 중 · 0명」", until(host, "() => document.getElementById('shareBtn').textContent.trim() === '공유 중 · 0명' && document.getElementById('shareBtn').classList.contains('on')"))
        host.click("#sharePop .share-row >> text=복사 >> nth=0")
        check("링크 복사", until(host, "async () => (await navigator.clipboard.readText()).includes('/s/')"))
        host.screenshot(path=str(OUT / "01_host_pop.png"))
        host.keyboard.press("Escape")
        check("Esc 로 닫힌다", until(host, "() => !document.getElementById('sharePop')"))

        # ---- 손님: 키 넣기 → 문서
        gctx = b.new_context(viewport={"width": 1100, "height": 900})
        guest = gctx.new_page()
        guest.on("console", lambda m: guest_err.append(m.text) if m.type == "error" else None)
        guest.on("pageerror", lambda e: guest_err.append(str(e)))
        guest.on("request", lambda r: guest_req.append(r.url))
        guest.goto(link)
        check("손님은 먼저 키 넣기 화면 — 문서는 안 보인다", until(guest, "() => !document.getElementById('gate').hidden && document.getElementById('scroller').hidden && document.title === '같이 쓰기'"))
        guest.fill("#nameIn", "이손님")
        guest.fill("#keyIn", "AAAA-AAAA-AAAA")
        guest.click("#joinBtn")
        check("틀린 키는 거절", until(guest, "() => !document.getElementById('gateErr').hidden && document.getElementById('gateErr').textContent.includes('키가 맞지 않습니다')") and guest.evaluate(PARAS) == 0)
        guest_err.clear()   # 403 응답의 「Failed to load resource」
        guest.fill("#keyIn", key.lower())
        guest.click("#joinBtn")
        check("맞는 키로 문서가 보인다", until(guest, "() => !document.getElementById('scroller').hidden && document.querySelectorAll('#doc .para').length > 5", timeout=20000))
        check("손님 화면의 문단 수 = 주인 화면의 문단 수", guest.evaluate(PARAS) == host.evaluate(PARAS), (guest.evaluate(PARAS), host.evaluate(PARAS)))
        bar = guest.evaluate("() => ({ name: document.getElementById('docName').textContent, host: document.getElementById('hostName').textContent, who: [...document.querySelectorAll('#people .who')].map((e) => e.textContent), save: document.getElementById('saveState').textContent, w: document.getElementById('doc').getBoundingClientRect().width })")
        check("위 줄 — 문서 이름 · 주인 · 사람들 · 반영 상태", bar["name"] == NAME and bar["host"] == "주인 김주인" and bar["save"] == "모두 반영됨" and any("(나)" in w for w in bar["who"]), bar)
        check("주인 단추가 「공유 중 · 1명」", until(host, "() => document.getElementById('shareBtn').textContent.trim() === '공유 중 · 1명'"))

        # ---- 글이 오간다 · 작성 중
        ids = guest.evaluate("() => [...document.querySelectorAll('#doc .para')].filter((p) => p.innerText.trim().length > 3).slice(0, 3).map((p) => p.dataset.id)")
        pa, pb = ids[0], ids[1]
        guest.click(f'.para[data-id="{pa}"]')
        guest.keyboard.press("End")
        guest.keyboard.type(" 손님이쓴글")
        check("손님이 쓴 글이 주인 화면에", until(host, HAS, [pa, "손님이쓴글"]), host.evaluate(TEXT, pa))
        check("손님 화면은 「모두 반영됨」", until(guest, "() => document.getElementById('saveState').textContent === '모두 반영됨'"))
        held = until(host, "(id) => { const p = document.querySelector(`.para[data-id=\"${id}\"]`); return p.classList.contains('share-held') && p.contentEditable === 'false' && p.dataset.shareWho === '이손님'; }", pa)
        check("손님이 작성 중인 문단은 주인 화면에서 못 고친다(색 띠)", held)
        host.click(f'.para[data-id="{pa}"]', force=True)
        check("그 문단을 누르면 누가 쓰는지 알린다", until(host, "() => document.getElementById('toast').textContent.includes('이손님 님이 작성 중')"))
        host.click("#shareBtn")
        check("창의 사람들 줄 — 이손님 — 작성 중", until(host, "() => [...document.querySelectorAll('#sharePeople .share-who')].some((e) => e.textContent.includes('이손님') && e.textContent.includes('작성 중'))"))
        host.screenshot(path=str(OUT / "02_host_held.png"))
        host.keyboard.press("Escape")
        host.click(f'.para[data-id="{pb}"]')
        host.keyboard.press("End")
        host.keyboard.type(" 주인이쓴글")
        check("주인이 쓴 글이 손님 화면에", until(guest, HAS, [pb, "주인이쓴글"]), guest.evaluate(TEXT, pb))
        check("주인이 작성 중인 문단은 손님 화면에서 못 고친다(이름표)", until(guest, "(id) => { const p = document.querySelector(`.para[data-id=\"${id}\"]`); return p.classList.contains('held') && p.contentEditable === 'false' && p.dataset.who === '김주인'; }", pb))
        guest.screenshot(path=str(OUT / "03_guest.png"))
        check("주인 화면의 글은 그대로(손님 글이 덮지 않는다)", "주인이쓴글" in host.evaluate(TEXT, pb) and "손님이쓴글" in host.evaluate(TEXT, pa))

        # ---- 줄 나누기 · 합치기 · 실행 취소
        n0 = host.evaluate(PARAS)
        guest.click(f'.para[data-id="{pa}"]')
        guest.keyboard.press("End")
        guest.keyboard.press("Enter")
        check("손님의 Enter — 손님 화면에 새 줄", until(guest, f"() => document.querySelectorAll('#doc .para').length === {n0 + 1}"))
        new = guest.evaluate("() => document.activeElement.dataset.id")
        check("커서가 새 줄에", bool(new) and new != pa, new)
        check("주인 화면에도 그 줄이 생긴다(그 블록만)", until(host, "([n, id]) => document.querySelectorAll('#doc .para').length === n && !!document.querySelector(`.para[data-id=\"${id}\"]`)", [n0 + 1, new]), host.evaluate(PARAS))
        check("주인이 쓰던 문단의 글은 그대로", "주인이쓴글" in host.evaluate(TEXT, pb))
        guest.keyboard.type("새줄글")
        check("새 줄에 쓴 글도 주인 화면에", until(host, HAS, [new, "새줄글"]))
        guest.keyboard.press("Home")
        guest.keyboard.press("Backspace")
        check("손님의 맨 앞 Backspace — 앞 줄에 합쳐진다", until(guest, f"() => document.querySelectorAll('#doc .para').length === {n0}") and until(guest, HAS, [pa, "새줄글"]))
        check("주인 화면에도 합쳐진다", until(host, "([n, id]) => document.querySelectorAll('#doc .para').length === n && document.querySelector(`.para[data-id=\"${id}\"]`).innerText.includes('새줄글')", [n0, pa]))
        guest.click("#docName")   # 손님이 커서를 뺀다
        check("주인의 실행 취소 단추가 켜져 있다(손님의 나누기·합치기도 문서의 편집)", until(host, "() => !document.getElementById('undoBtn').disabled"))
        host.click("#undoBtn")
        check("주인의 실행 취소 — 손님 화면이 문서를 다시 읽어 맞춘다", until(guest, f"() => document.querySelectorAll('#doc .para').length === {n0 + 1}", timeout=12000), guest.evaluate(PARAS))
        check("주인 화면도 같은 수", until(host, f"() => document.querySelectorAll('#doc .para').length === {n0 + 1}"))
        # 손님이 쓰고 있는 줄을 주인의 실행 취소가 없앤다 — 손님 화면은 「공유가 끝났습니다」 가 아니라 문서를 다시 읽고 이어 간다
        n1 = host.evaluate(PARAS)
        guest.click(f'.para[data-id="{pb}"]')
        guest.keyboard.press("End")
        guest.keyboard.press("Enter")
        check("손님이 또 줄을 나눈다", until(guest, f"() => document.querySelectorAll('#doc .para').length === {n1 + 1}") and until(host, f"() => document.querySelectorAll('#doc .para').length === {n1 + 1}"))
        doomed = guest.evaluate("() => document.activeElement.dataset.id")
        guest.keyboard.type("곧사라질줄")
        check("그 줄에 쓴 글이 주인 화면에", until(host, HAS, [doomed, "곧사라질줄"]))
        host.click("#undoBtn")
        guest.keyboard.type("더씀")   # 없어진 줄에 계속 친다
        check("없어진 줄에 치던 손님 — 문서를 다시 읽고 이어 간다(끝난 것으로 보지 않는다)",
              until(guest, "([n, id]) => document.getElementById('closed').hidden && !document.getElementById('scroller').hidden && document.querySelectorAll('#doc .para').length === n && !document.querySelector(`.para[data-id=\"${id}\"]`)", [n1, doomed], timeout=12000),
              guest.evaluate("() => ({ closed: document.getElementById('closed').hidden, n: document.querySelectorAll('#doc .para').length, save: document.getElementById('saveState').textContent, toast: document.getElementById('toast').textContent })"))
        guest_err.clear()   # 없어진 줄에 보낸 글의 404
        guest.click("#docName")
        host.click(f'.para[data-id="{pb}"]')
        host.keyboard.press("End")
        host.keyboard.type(" 그뒤주인글")
        check("그 뒤에도 주인이 쓴 글이 손님 화면에 온다", until(guest, HAS, [pb, "그뒤주인글"]))
        check("손님 화면의 반영 상태가 정상으로 돌아온다", until(guest, "() => document.getElementById('saveState').textContent === '모두 반영됨'"))
        host.click("#fileName", force=True)   # 주인이 커서를 뺀다

        # ---- 공유폴더에 다시 쓰기
        end, again = time.time() + 20, first
        while time.time() < end and again == first:
            time.sleep(0.5)
            again = (FOLDER / NAME).read_bytes()
        check("바뀐 문서는 조용해지면 공유폴더의 파일에 다시 쓴다", again != first and again[:2] == b"PK")
        host.click("#shareBtn")
        check("창의 저장 줄 — 「… 저장됨」", until(host, "() => (document.getElementById('shareSaved') || {}).textContent?.endsWith('저장됨')", timeout=12000), host.evaluate("() => (document.getElementById('shareSaved') || {}).textContent"))

        # ---- 키 새로 만들기 · 끄기
        host.click("#sharePop .share-acts >> text=키 새로 만들기")
        check("새 키가 보인다", until(host, "(old) => { const k = document.getElementById('shareKey'); return !!k && k.value !== old && k.value.length === 14; }", key))
        key2 = host.input_value("#shareKey")
        check("손님은 키 넣기로 돌아간다", until(guest, "() => !document.getElementById('gate').hidden && document.getElementById('scroller').hidden && document.getElementById('gateNote').textContent.includes('키')", timeout=10000))
        guest_err.clear()   # 401 응답의 「Failed to load resource」
        guest.fill("#keyIn", key)
        guest.click("#joinBtn")
        check("옛 키는 안 된다", until(guest, "() => !document.getElementById('gateErr').hidden"))
        guest_err.clear()
        guest.fill("#keyIn", key2)
        guest.click("#joinBtn")
        check("새 키로 다시 들어온다", until(guest, "() => !document.getElementById('scroller').hidden && document.querySelectorAll('#doc .para').length > 5", timeout=20000))
        guest.click("#leaveBtn")
        check("「나가기」 — 키 넣기로 돌아가고 이름은 남는다", until(guest, "() => !document.getElementById('gate').hidden && document.getElementById('gateNote').textContent.includes('나갔습니다') && document.getElementById('nameIn').value === '이손님'"))
        check("나간 손님은 주인 단추에서 빠진다", until(host, "() => document.getElementById('shareBtn').textContent.trim() === '공유 중 · 0명'", timeout=30000))
        guest.fill("#keyIn", key2)
        guest.click("#joinBtn")
        check("나간 뒤 다시 들어온다", until(guest, "() => !document.getElementById('scroller').hidden && document.querySelectorAll('#doc .para').length > 5", timeout=20000))
        host.click("#sharePop .share-acts >> text=공유 끄기")
        check("끄면 단추가 「공유」 로", until(host, "() => document.getElementById('shareBtn').textContent.trim() === '공유' && !document.querySelector('.para.share-held')"))
        check("손님 화면은 「공유가 끝났습니다」", until(guest, "() => !document.getElementById('closed').hidden && document.getElementById('scroller').hidden", timeout=10000))
        left = sorted(p.name for p in FOLDER.iterdir())
        check("링크 바로가기는 지우고 저장본은 남긴다", left == [NAME], left)
        closed = False
        for _ in range(20):
            try:
                requests.get(link + "/info", timeout=1)
                time.sleep(0.3)
            except requests.RequestException:
                closed = True
                break
        check("켜진 공유가 없으면 공유 포트를 닫는다", closed)
        guest_err.clear()   # 닫힌 포트로 간 마지막 읽기
        if not host.evaluate("() => !!document.getElementById('sharePop')"):   # 끄기를 누른 창은 열린 채 「켜기」 꼴로 바뀐다 — 닫혀 있을 때만 연다
            host.click("#shareBtn")
        again = until(host, "() => !!document.getElementById('shareFolder')") and host.evaluate("() => ({ folder: document.getElementById('shareFolder').value, host: document.getElementById('shareHost').value })")
        check("끈 뒤 창 — 지난번 공유폴더와 이름이 채워져 있다", bool(again) and again["folder"] == str(FOLDER) and again["host"] == "김주인", again)
        host.set_viewport_size({"width": 700, "height": 800})
        host.wait_for_timeout(300)
        box = host.evaluate("""() => { const p = document.getElementById('sharePop'), b = document.getElementById('shareBtn'), bar = document.querySelector('.topbar');
          if (!p) return { gone: true, btn: !!b && b.getClientRects().length > 0 };
          const r = p.getBoundingClientRect(), over = () => bar.scrollWidth - bar.clientWidth, withBtn = over();
          b.style.display = 'none'; const without = over(); b.style.display = '';   // 단추가 없을 때의 상단 바 넘침(단추 탓인지 가른다)
          return { l: r.left, r: r.right, vw: innerWidth, over: p.scrollWidth > p.clientWidth + 1, bar: withBtn, bar0: without, w: Math.round(b.getBoundingClientRect().width) }; }""")
        check("좁은 화면(700px) — 창이 화면 안 · 넘침 없음 · 「공유」 단추가 상단 바를 넘치게 하지 않는다", not box.get("gone") and box["l"] >= 0 and box["r"] <= box["vw"] and not box["over"] and box["bar"] <= max(box["bar0"], 1), box)
        host.screenshot(path=str(OUT / "04_host_narrow.png"))
        host.keyboard.press("Escape")
        host.set_viewport_size({"width": 1500, "height": 900})

        out = [u for u in guest_req if not (u.startswith(f"http://127.0.0.1:{SHARE_PORT}/s/") or u.startswith(f"http://127.0.0.1:{SHARE_PORT}/share-static/"))]
        check("손님 화면은 /s/ · /share-static/ 밖으로 요청하지 않는다", not out, out[:5])
        check("주인 화면 콘솔 오류 0", not [e for e in host_err if "Failed to load resource" not in e], host_err[:5])
        check("손님 화면 콘솔 오류 0(CSP 위반 포함)", not [e for e in guest_err if "Failed to load resource" not in e], guest_err[:5])
        b.close()


try:
    main()
finally:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()

print(f"\n{'실패 ' + str(len(fails)) + '개: ' + ' / '.join(fails) if fails else '모두 통과'}")
sys.exit(1 if fails else 0)
